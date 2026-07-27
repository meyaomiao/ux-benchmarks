"""End-to-end probe pipeline: queries -> adapters -> scorer -> shortlist.

This wires the pieces built across #14-#19 into one runnable chain:

    query_expansion (build_query_bundle)               # what to search for
        -> [adapter.fetch(...) for each adapter]       # raw Candidates (#17 #18)
        -> scorer.score(...)                           # relevance verdict (#19)
        -> keep passers                                # score >= RELEVANCE_FLOOR

Multiple adapters (e.g. help-docs text + interactive demo screenshots) are run
and their Candidates are merged before scoring. Text and image candidates are
scored in their respective modes by the dual-mode scorer (#19/#45).

Adapter(s) + scorer are injected (defaults: HelpDocsAdapter + InteractiveDemoAdapter,
each with mock fallback via settings.use_collection_mock) so this is testable
offline with fakes. Pass `adapter=` (singular) for backward-compat with tests
that inject a single fake.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.m2_mapping.mapping_service import get_mapping_card_by_cell
from app.services.m3_collection.adapters.help_docs import HelpDocsAdapter
from app.services.m3_collection.adapters.interactive_demo import (
    InteractiveDemoAdapter,
    capture_page_screenshots,
)
from app.services.m3_collection.adapters.web_source import WebSourceAdapter
from app.services.m3_collection.contracts import (
    RELEVANCE_FLOOR,
    Adapter,
    Candidate,
    Score,
    Scorer,
    SourceType,
)
from app.services.m3_collection.interaction_pattern import (
    abstract_interaction_pattern,
    abstracted_intent,
    needs_abstraction,
)
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection.scoring.relevance_scorer import (
    PRODUCT_MATCH_GATE,
    RelevanceScorer,
)
from app.services.m3_collection.search_service import resolve_queries_to_urls

# Official buckets must stay on the competitor's own domain — see
# resolve_queries_to_urls(allow_unanchored_fallback=...).
_OFFICIAL_BUCKETS = {SourceType.HELP_DOCS, SourceType.INTERACTIVE_DEMO}

# Near-threshold rescore window. A text candidate scoring within this much of
# the floor is one missing screenshot away from passing: text-only candidates
# are structurally capped on fidelity + evidence_directness (0.10 + 0.20 of the
# weight), so the gap is an artefact of having no image, not of being irrelevant.
_RESCORE_BAND = 0.12

# Only rescore candidates the scorer already reads as the RIGHT product. Below
# the gate a screenshot cannot rescue the candidate anyway, so capturing one
# would just burn browser time and a vision call.
_RESCORE_MIN_PRODUCT_MATCH = PRODUCT_MATCH_GATE

# Cap on how many candidates one probe will re-screenshot. Each costs a page
# load plus a vision call, so this bounds the added latency per probe.
_RESCORE_MAX = 4


@dataclass
class ProbeResult:
    """Outcome of one probe pass over a (cell, competitor) pair."""
    cell_id: UUID
    competitor_id: UUID
    candidates_found: int
    scored: list[tuple[Candidate, Score]]  # every candidate + its score
    passed: list[tuple[Candidate, Score]]  # subset with score >= floor

    @property
    def has_passers(self) -> bool:
        return len(self.passed) > 0


def run_probe_pipeline(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    *,
    adapter: Adapter | None = None,         # singular — backward compat for tests
    adapters: list[Adapter] | None = None,  # multi-adapter — takes precedence
    scorer: Scorer | None = None,
    per_bucket_limit: int = 10,
) -> ProbeResult:
    """Fetch candidates from all adapters, score them, and return the passers.

    Adapter resolution order:
      1. `adapters` list if provided
      2. `adapter` singular if provided (wrapped in a list)
      3. default: [HelpDocsAdapter, InteractiveDemoAdapter]

    Does NOT change cell state or persist anything — the caller (probe_cycle)
    owns state transitions. Missing mapping card => no scoring context, treated
    as zero passers.
    """
    if adapters is not None:
        _adapters: list[Adapter] = adapters
    elif adapter is not None:
        _adapters = [adapter]
    else:
        # help docs + interactive demo + community(forums/Q&A) + generic(blogs/
        # articles). The web adapters consume the community/generic buckets that
        # were previously computed but never fetched — this is what surfaces the
        # non-official-site evidence (forums, knowledge communities, reviews).
        _adapters = [
            HelpDocsAdapter(),
            InteractiveDemoAdapter(),
            WebSourceAdapter(SourceType.COMMUNITY),
            WebSourceAdapter(SourceType.GENERIC),
        ]

    scorer = scorer or RelevanceScorer()

    # 1. What to search for (query expansion, #15).
    bundle = build_query_bundle(db, cell_id, competitor_id)

    # 2. Run all adapters; route each to the right query bucket.
    #    In live mode, resolve query strings to real URLs via the search service
    #    before passing to adapters (which expect http(s) URLs in live mode).
    all_candidates: list[Candidate] = []
    for adp in _adapters:
        queries = getattr(bundle, adp.source_type.value, []) or bundle.generic
        if not settings.use_collection_mock:
            # Resolve search-operator strings (e.g. "site:help.* setup") to URLs.
            queries = resolve_queries_to_urls(
                queries,
                max_total=per_bucket_limit * 2,
                allow_unanchored_fallback=adp.source_type not in _OFFICIAL_BUCKETS,
            )
        try:
            found = adp.fetch(cell_id, competitor_id, queries, limit=per_bucket_limit)
            all_candidates.extend(found)
        except Exception as exc:  # noqa: BLE001 — one failing adapter doesn't kill others
            import logging
            logging.getLogger(__name__).warning(
                "adapter %s failed for cell %s: %s",
                type(adp).__name__, cell_id, exc,
            )

    # 3. Scoring context from the mapping card (#11 / #2).
    card = get_mapping_card_by_cell(db, cell_id)
    intent = card.intent_definition if card else ""
    inclusion = (card.inclusion_criteria if card else "") or ""
    exclusion = (card.exclusion_criteria if card else "") or ""

    # Target product name — this is a competitor-scoped tool, so the scorer must
    # know WHICH product a cell belongs to (a Notion cell rejects Adobe evidence).
    # Without it, product_match degenerates to "is this a real product page?".
    # Best-effort: a missing db/entity just leaves product_name="" (gate inert),
    # matching how the rest of the pipeline degrades gracefully without context.
    product_name = ""
    competitor_type = ""
    if db is not None:
        try:
            from sqlalchemy import select as _select

            from app.models.m0_registry import CompetitorEntity
            _comp = db.execute(
                _select(CompetitorEntity).where(CompetitorEntity.id == competitor_id)
            ).scalar_one_or_none()
            product_name = (_comp.canonical_name if _comp else "") or ""
            competitor_type = (_comp.competitor_type if _comp else "") or ""
        except Exception:  # noqa: BLE001 — context lookup must never kill a probe
            product_name = ""
            competitor_type = ""

    # Indirect / cross-industry competitors are scored on interaction STRUCTURE,
    # not on our domain intent. build_query_bundle already searched the abstracted
    # pattern for these pairs; if the rubric still demanded the industry intent
    # (state_match 0.35 + product_match 0.20 = the whole 0.55 floor), every found
    # artifact would score 0 and the empty cells would just become passed=0 cells.
    # Same cached phrase on both sides, so query and rubric cannot drift.
    if db is not None and needs_abstraction(competitor_type):
        try:
            from sqlalchemy import select as _select2

            from app.models.m1_grid import GridCell
            _cell = db.execute(
                _select2(GridCell).where(GridCell.id == cell_id)
            ).scalar_one_or_none()
            if _cell is not None:
                pattern = abstract_interaction_pattern(
                    _cell.page_state, _cell.journey_stage, _cell.jtbd or "",
                )
                if pattern:
                    intent = abstracted_intent(pattern, intent)
                    # The criteria are written in domain language too, so keeping
                    # them would re-impose the industry filter the pattern just
                    # removed.
                    inclusion = ""
                    exclusion = ""
        except Exception:  # noqa: BLE001 — abstraction must never kill a probe
            pass

    # 4. Score each candidate (#19) and keep the passers.
    #    Text and image candidates are scored in their respective modes
    #    by the dual-mode scorer (PR #45).
    # Score all candidates CONCURRENTLY — each score() is an LLM API call
    # (I/O-bound), so a thread pool turns N serial calls into ceil(N/workers)
    # rounds. This is the main lever cutting a probe from ~12min to ~1min.
    from concurrent.futures import ThreadPoolExecutor

    def _score_one(cand: Candidate) -> tuple[Candidate, Score]:
        return cand, scorer.score(
            cand,
            intent_definition=intent,
            inclusion_criteria=inclusion,
            exclusion_criteria=exclusion,
            product_name=product_name,
        )

    scored: list[tuple[Candidate, Score]] = []
    passed: list[tuple[Candidate, Score]] = []
    if all_candidates:
        with ThreadPoolExecutor(max_workers=min(8, len(all_candidates))) as pool:
            for cand, score in pool.map(_score_one, all_candidates):
                scored.append((cand, score))
                if score.passed:
                    passed.append((cand, score))

        # 4b. Near-threshold rescore: screenshot the right-product text
        # candidates that died just under the floor, then score them again in
        # image mode. Both scores stay in `scored`, so the diagnostics log keeps
        # the full audit trail of why a candidate ended up where it did.
        rescored = _rescore_near_threshold(scored, _score_one)
        for cand, score in rescored:
            scored.append((cand, score))
            if score.passed:
                passed.append((cand, score))

    # Highest score first — image candidates tend to rank higher (TEXT_ONLY_CEILING).
    passed.sort(key=lambda cs: cs[1].score, reverse=True)

    return ProbeResult(
        cell_id=cell_id,
        competitor_id=competitor_id,
        candidates_found=len(all_candidates),
        scored=scored,
        passed=passed,
    )


def _rescore_near_threshold(
    scored: list[tuple[Candidate, Score]],
    score_one,
) -> list[tuple[Candidate, Score]]:
    """Screenshot near-miss text candidates and re-score them in image mode.

    A candidate qualifies when it has no image, did not pass, already reads as
    the target product (``product_match >= _RESCORE_MIN_PRODUCT_MATCH``), and
    landed within ``_RESCORE_BAND`` of the floor. Those are exactly the ones
    whose only deficit is "no screenshot".

    Returns the new (candidate, score) pairs — the originals are left untouched.
    Best-effort: any failure yields an empty list rather than breaking the probe.
    """
    near_misses = [
        cand for cand, score in scored
        if cand.image_path is None
        and not score.passed
        and score.rubric.product_match >= _RESCORE_MIN_PRODUCT_MATCH
        and RELEVANCE_FLOOR - _RESCORE_BAND <= score.score < RELEVANCE_FLOOR
    ]
    if not near_misses:
        return []

    # Highest first, so the budget goes to the closest misses.
    by_score = {cand.candidate_id: score.score for cand, score in scored}
    near_misses.sort(key=lambda c: by_score[c.candidate_id], reverse=True)
    near_misses = near_misses[:_RESCORE_MAX]

    try:
        shots = capture_page_screenshots([c.source_url for c in near_misses])
    except Exception as exc:  # noqa: BLE001 — rescore is an upgrade, not a duty
        import logging
        logging.getLogger(__name__).warning("near-threshold capture failed: %s", exc)
        return []

    with_images = [
        replace(cand, image_path=shots[cand.source_url])
        for cand in near_misses
        if cand.source_url in shots
    ]
    if not with_images:
        return []

    from concurrent.futures import ThreadPoolExecutor

    out: list[tuple[Candidate, Score]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(with_images))) as pool:
        out.extend(pool.map(score_one, with_images))
    return out
