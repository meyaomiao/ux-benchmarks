"""End-to-end probe pipeline: queries -> adapters -> scorer -> shortlist.

This wires the pieces built across #14-#19 into one runnable chain:

    query_expansion (build_query_bundle)               # what to search for
        -> [adapter.fetch(...) for each adapter]       # raw Candidates (#17 #18)
        -> scorer.score(...)                           # relevance verdict (#19)
        -> keep passers                                # score >= RELEVANCE_FLOOR

Multiple adapters (e.g. help-docs text + interactive demo screenshots) are run
and their Candidates are merged before scoring. Text and image candidates are
scored in their respective modes by the dual-mode scorer (#19/#45).

Adapter(s) + scorer are injected (defaults: agentic site, help docs,
interactive demos, community and generic web, with offline mock fallbacks via
settings.use_collection_mock) so this is testable offline with fakes. Pass
`adapter=` (singular) for backward-compat with tests that inject a single fake.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field, replace
from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.m2_mapping.mapping_service import get_mapping_card_by_cell
from app.services.m3_collection.adapters.agentic_site import AgenticSiteAdapter
from app.services.m3_collection.adapters.help_docs import HelpDocsAdapter
from app.services.m3_collection.adapters.interactive_demo import (
    InteractiveDemoAdapter,
    capture_page_screenshots,
)
from app.services.m3_collection.adapters.web_source import WebSourceAdapter
from app.services.m3_collection.agentic_site import (
    MAX_CANDIDATES,
    canonical_url,
)
from app.services.m3_collection.content_fetch import (
    DEFAULT_RENDER_LIMIT_PER_ADAPTER,
    DEFAULT_RENDER_LIMIT_PER_PROBE,
    RenderBudget,
)
from app.services.m3_collection.contracts import (
    RELEVANCE_FLOOR,
    Adapter,
    Candidate,
    RubricBreakdown,
    Score,
    Scorer,
    SourceType,
)
from app.services.m3_collection.interaction_pattern import (
    abstract_interaction_pattern,
    abstracted_intent,
    needs_abstraction,
)
from app.services.m3_collection.probe_observability import ProbeTelemetry
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection.scoring.relevance_scorer import (
    GPT_ERROR_PREFIX,
    PRODUCT_MATCH_GATE,
    RelevanceScorer,
)
from app.services.m3_collection.search_service import resolve_queries_to_urls

# Official buckets must stay on the competitor's own domain — see
# resolve_queries_to_urls(allow_unanchored_fallback=...).
_OFFICIAL_BUCKETS = {
    SourceType.HELP_DOCS,
    SourceType.AGENTIC_SITE,
    SourceType.INTERACTIVE_DEMO,
}

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

# Live scoring is deliberately bounded below the Celery task's 720-second soft
# limit. The cap includes Agentic retries and near-threshold image rescoring.
MAX_LIVE_SCORING_CALLS_PER_PROBE = 18
MAX_LIVE_SCORING_SECONDS = 300
AGENTIC_LIVE_SCORE_ATTEMPTS = 2

_LIVE_SCORING_SOURCE_PRIORITY = {
    SourceType.AGENTIC_SITE: 0,
    SourceType.INTERACTIVE_DEMO: 1,
    SourceType.HELP_DOCS: 2,
    SourceType.COMMUNITY: 3,
    SourceType.GENERIC: 4,
}


@dataclass(frozen=True)
class SourceBudget:
    max_searches: int
    max_urls: int
    max_candidates: int


# UI-rich sources run first and receive explicit, non-transferable budgets. The
# table is also the cost contract for one default probe: at most 10 web searches
# and 40 candidates before cross-source URL deduplication.
DEFAULT_SOURCE_BUDGETS = {
    SourceType.AGENTIC_SITE: SourceBudget(0, 0, MAX_CANDIDATES),
    SourceType.INTERACTIVE_DEMO: SourceBudget(3, 6, 6),
    SourceType.HELP_DOCS: SourceBudget(2, 12, 12),
    SourceType.COMMUNITY: SourceBudget(2, 8, 8),
    SourceType.GENERIC: SourceBudget(3, 10, 10),
}
MAX_SEARCH_CALLS_PER_PROBE = sum(
    budget.max_searches for budget in DEFAULT_SOURCE_BUDGETS.values()
)
MAX_INITIAL_CANDIDATES_PER_PROBE = sum(
    budget.max_candidates for budget in DEFAULT_SOURCE_BUDGETS.values()
)


@dataclass
class ProbeResult:
    """Outcome of one probe pass over a (cell, competitor) pair."""
    cell_id: UUID
    competitor_id: UUID
    candidates_found: int
    scored: list[tuple[Candidate, Score]]  # every candidate + its score
    passed: list[tuple[Candidate, Score]]  # subset with score >= floor
    agentic_stats: dict[str, int | str] = field(default_factory=dict)

    @property
    def has_passers(self) -> bool:
        return len(self.passed) > 0


def _live_scoring_priority(candidate: Candidate) -> tuple[int, int]:
    return (
        _LIVE_SCORING_SOURCE_PRIORITY.get(candidate.source_type, 99),
        0 if candidate.image_path else 1,
    )


def _not_scored(candidate: Candidate, reason: str) -> Score:
    return Score(
        candidate_id=candidate.candidate_id,
        score=0.0,
        passed=False,
        evidence_type=candidate.evidence_type_hint,
        rubric=RubricBreakdown(),
        reasoning=f"[not-scored:{reason}] live scoring budget exhausted",
        scored_by=f"not-scored:{reason}",
    )


def run_probe_pipeline(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    *,
    adapter: Adapter | None = None,         # singular — backward compat for tests
    adapters: list[Adapter] | None = None,  # multi-adapter — takes precedence
    scorer: Scorer | None = None,
    per_bucket_limit: int = 10,
    telemetry: ProbeTelemetry | None = None,
) -> ProbeResult:
    """Fetch candidates from all adapters, score them, and return the passers.

    Adapter resolution order:
      1. `adapters` list if provided
      2. `adapter` singular if provided (wrapped in a list)
      3. default: agentic site + help docs + interactive demo + community + generic web

    Does NOT change cell state or persist anything — the caller (probe_cycle)
    owns state transitions. Missing mapping card => no scoring context, treated
    as zero passers.
    """
    using_default_adapters = adapters is None and adapter is None
    if adapters is not None:
        _adapters: list[Adapter] = adapters
    elif adapter is not None:
        _adapters = [adapter]
    else:
        _adapters = []

    scorer = scorer or RelevanceScorer()
    bounded_live_scoring = (
        isinstance(scorer, RelevanceScorer) and not settings.use_collection_mock
    )

    # 1. What to search for (query expansion, #15).
    bundle = build_query_bundle(db, cell_id, competitor_id)

    # 2. Scoring and exploration context from the mapping card and competitor.
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
    official_domain = None
    help_center_domain = None
    if db is not None:
        try:
            from sqlalchemy import select as _select

            from app.models.m0_registry import CompetitorEntity
            _comp = db.execute(
                _select(CompetitorEntity).where(CompetitorEntity.id == competitor_id)
            ).scalar_one_or_none()
            product_name = (_comp.canonical_name if _comp else "") or ""
            competitor_type = (_comp.competitor_type if _comp else "") or ""
            official_domain = getattr(_comp, "official_domain", None) if _comp else None
            help_center_domain = (
                getattr(_comp, "help_center_domain", None) if _comp else None
            )
        except SoftTimeLimitExceeded:
            raise
        except Exception:  # noqa: BLE001 — context lookup must never kill a probe
            product_name = ""
            competitor_type = ""
            official_domain = None
            help_center_domain = None

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
        except SoftTimeLimitExceeded:
            raise
        except Exception:  # noqa: BLE001 — abstraction must never kill a probe
            pass

    if using_default_adapters:
        # Async probes are routed at the parent-task level to the dedicated
        # browser queue. The agentic channel is live-only; deterministic mock
        # runs retain the existing adapter set and never use browser or relay.
        render_budget = RenderBudget(DEFAULT_RENDER_LIMIT_PER_PROBE)
        if not settings.use_collection_mock:
            _adapters.append(
                AgenticSiteAdapter(
                    competitor_name=product_name,
                    intent=intent,
                    official_domain=official_domain,
                    help_center_domain=help_center_domain,
                )
            )
        _adapters.extend(
            [
                InteractiveDemoAdapter(),
                HelpDocsAdapter(
                    render_limit=DEFAULT_RENDER_LIMIT_PER_ADAPTER,
                    render_budget=render_budget,
                ),
                WebSourceAdapter(
                    SourceType.COMMUNITY,
                    render_limit=DEFAULT_RENDER_LIMIT_PER_ADAPTER,
                    render_budget=render_budget,
                ),
                WebSourceAdapter(
                    SourceType.GENERIC,
                    render_limit=DEFAULT_RENDER_LIMIT_PER_ADAPTER,
                    render_budget=render_budget,
                ),
            ]
        )
        if telemetry is not None:
            telemetry.source_budgets = {
                source_type.value: asdict(budget)
                for source_type, budget in DEFAULT_SOURCE_BUDGETS.items()
            }

    # 3. Run all adapters, then collapse cross-channel URL duplicates before
    # scoring so the same page consumes only one vision call and database row.
    all_candidates: list[Candidate] = []
    agentic_stats: dict[str, int | str] = {}
    for adp in _adapters:
        source_started = time.monotonic()
        source_name = adp.source_type.value
        source_budget = (
            DEFAULT_SOURCE_BUDGETS.get(adp.source_type)
            if using_default_adapters
            else None
        )
        candidate_limit = (
            source_budget.max_candidates if source_budget else per_bucket_limit
        )
        queries = []
        search_metrics: dict[str, int] = {}
        found: list[Candidate] = []
        source_status = "ok"
        error_type = None
        if getattr(adp, "uses_search_queries", True):
            queries = getattr(bundle, adp.source_type.value, []) or bundle.generic
        queries_available = len(queries)
        try:
            if not settings.use_collection_mock and getattr(
                adp, "uses_search_queries", True
            ):
                queries = resolve_queries_to_urls(
                    queries,
                    max_total=(
                        source_budget.max_urls
                        if source_budget
                        else per_bucket_limit * 2
                    ),
                    max_searches=(
                        source_budget.max_searches if source_budget else 3
                    ),
                    allow_unanchored_fallback=adp.source_type not in _OFFICIAL_BUCKETS,
                    metrics=search_metrics,
                )
            found = adp.fetch(cell_id, competitor_id, queries, limit=candidate_limit)
            all_candidates.extend(found)
        except SoftTimeLimitExceeded:
            source_status = "soft_timeout"
            error_type = "SoftTimeLimitExceeded"
            raise
        except Exception as exc:  # noqa: BLE001 - one adapter must not kill the others
            source_status = "error"
            error_type = type(exc).__name__
            import logging

            logging.getLogger(__name__).warning(
                "adapter %s failed for cell %s: %s",
                type(adp).__name__, cell_id, exc,
            )
        finally:
            if isinstance(adp, AgenticSiteAdapter):
                agentic_stats = getattr(adp, "last_stats", {}) or {}
                if telemetry is not None:
                    telemetry.agentic_stats = dict(agentic_stats)
                    telemetry.agentic_trace = list(getattr(adp, "last_trace", []))
            if telemetry is not None:
                adapter_stats = getattr(adp, "last_stats", {}) or {}
                browser_pages = adapter_stats.get(
                    "browser_pages", adapter_stats.get("pages_opened", 0)
                )
                telemetry.source_stats[source_name] = {
                    "queries_available": queries_available,
                    "search_calls": int(search_metrics.get("search_calls", 0)),
                    "urls_found": int(search_metrics.get("urls_found", 0)),
                    "candidates_found": len(found),
                    "browser_pages": int(browser_pages),
                    "duration_ms": int((time.monotonic() - source_started) * 1000),
                    "status": source_status,
                    "error_type": error_type,
                }
                telemetry.candidates_found = len(_dedupe_candidates(all_candidates))

    all_candidates = _dedupe_candidates(all_candidates)
    if bounded_live_scoring:
        # Keep expensive live calls focused on evidence that can actually prove
        # the UI state. Stable sorting preserves adapter/search rank within each
        # source and image class.
        all_candidates.sort(key=_live_scoring_priority)

    # 4. Score each candidate (#19) and keep the passers.
    #    Text and image candidates are scored in their respective modes
    #    by the dual-mode scorer (PR #45).
    scoring_started = time.monotonic()
    live_scoring_calls = 0

    def _live_budget_available() -> bool:
        return (
            live_scoring_calls < MAX_LIVE_SCORING_CALLS_PER_PROBE
            and time.monotonic() - scoring_started < MAX_LIVE_SCORING_SECONDS
        )

    def _invoke_scorer(cand: Candidate) -> Score:
        nonlocal live_scoring_calls
        if bounded_live_scoring:
            live_scoring_calls += 1
        if telemetry is not None:
            telemetry.scoring_calls += 1
        score = scorer.score(
            cand,
            intent_definition=intent,
            inclusion_criteria=inclusion,
            exclusion_criteria=exclusion,
            product_name=product_name,
        )
        if telemetry is not None:
            telemetry.scored_candidates.append((cand, score))
        return score

    def _score_one(cand: Candidate) -> tuple[Candidate, Score]:
        if bounded_live_scoring and not _live_budget_available():
            score = _not_scored(cand, "budget")
            if telemetry is not None:
                telemetry.scored_candidates.append((cand, score))
        else:
            score = _invoke_scorer(cand)
            attempts = 1
            while (
                bounded_live_scoring
                and bool(settings.gpt_api_key)
                and cand.source_type == SourceType.AGENTIC_SITE
                and score.scored_by.startswith(GPT_ERROR_PREFIX)
                and attempts < AGENTIC_LIVE_SCORE_ATTEMPTS
                and _live_budget_available()
            ):
                score = _invoke_scorer(cand)
                attempts += 1
        if telemetry is not None:
            telemetry.scored_count += 1
            if score.passed:
                telemetry.passed_count += 1
        return cand, score

    scored: list[tuple[Candidate, Score]] = []
    passed: list[tuple[Candidate, Score]] = []
    for cand in all_candidates:
        candidate, score = _score_one(cand)
        scored.append((candidate, score))
        if score.passed:
            passed.append((candidate, score))

    if all_candidates:
        # 4b. Near-threshold rescore: screenshot the right-product text
        # candidates that died just under the floor, then score them again in
        # image mode. Both scores stay in `scored`, so the diagnostics log keeps
        # the full audit trail of why a candidate ended up where it did.
        rescored = _rescore_near_threshold(scored, _score_one, telemetry=telemetry)
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
        agentic_stats=agentic_stats,
    )


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    """Keep one candidate per normalized URL, preferring richer evidence."""
    selected: dict[str, tuple[int, Candidate]] = {}
    for index, candidate in enumerate(candidates):
        key = canonical_url(candidate.source_url)
        current = selected.get(key)
        if current is None or _candidate_quality(candidate) > _candidate_quality(current[1]):
            selected[key] = (current[0] if current else index, candidate)
    return [candidate for _, candidate in sorted(selected.values(), key=lambda item: item[0])]


def _candidate_quality(candidate: Candidate) -> tuple[bool, int, int]:
    return (
        bool(candidate.image_path),
        len(candidate.text_content),
        len(candidate.title) + len(candidate.snippet),
    )


def _rescore_near_threshold(
    scored: list[tuple[Candidate, Score]],
    score_one,
    *,
    telemetry: ProbeTelemetry | None = None,
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
    if telemetry is not None:
        telemetry.rescore_render_attempts += len(near_misses)

    try:
        shots = capture_page_screenshots([c.source_url for c in near_misses])
    except SoftTimeLimitExceeded:
        raise
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

    return [score_one(candidate) for candidate in with_images]
