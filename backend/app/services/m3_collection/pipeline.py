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

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.m2_mapping.mapping_service import get_mapping_card_by_cell
from app.services.m3_collection.adapters.help_docs import HelpDocsAdapter
from app.services.m3_collection.adapters.interactive_demo import InteractiveDemoAdapter
from app.services.m3_collection.adapters.web_source import WebSourceAdapter
from app.services.m3_collection.contracts import Adapter, Candidate, Score, Scorer, SourceType
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer
from app.services.m3_collection.search_service import resolve_queries_to_urls


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
            queries = resolve_queries_to_urls(queries, max_total=per_bucket_limit * 2)
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

    # 4. Score each candidate (#19) and keep the passers.
    #    Text and image candidates are scored in their respective modes
    #    by the dual-mode scorer (PR #45).
    scored: list[tuple[Candidate, Score]] = []
    passed: list[tuple[Candidate, Score]] = []
    for cand in all_candidates:
        score = scorer.score(
            cand,
            intent_definition=intent,
            inclusion_criteria=inclusion,
            exclusion_criteria=exclusion,
        )
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
