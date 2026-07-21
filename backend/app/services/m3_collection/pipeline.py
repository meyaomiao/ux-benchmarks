"""End-to-end probe pipeline: queries -> adapter -> scorer -> shortlist.

This wires the pieces built across #14-#19 into one runnable chain:

    query_expansion (build_query_bundle)      # what to search for
        -> adapter.fetch(...)                 # raw Candidates (#17)
        -> scorer.score(...)                  # relevance verdict (#19)
        -> keep passers                       # score >= RELEVANCE_FLOOR

Persistence of accepted assets and dedup/shortlist ranking are separate issues
(#20 dedup, #22 asset store), so this returns the scored result in memory and
the caller decides the next state (SHORTLIST_READY vs REJECTED_EMPTY).

Adapter + scorer are injected (default to the real classes, which themselves
fall back to mock mode via settings.use_collection_mock) so this orchestration
is unit-testable offline with fakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.m2_mapping.mapping_service import get_mapping_card_by_cell
from app.services.m3_collection.adapters.help_docs import HelpDocsAdapter
from app.services.m3_collection.contracts import Adapter, Candidate, Score, Scorer
from app.services.m3_collection.query_expansion import build_query_bundle
from app.services.m3_collection.scoring.relevance_scorer import RelevanceScorer


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
    adapter: Adapter | None = None,
    scorer: Scorer | None = None,
    per_bucket_limit: int = 10,
) -> ProbeResult:
    """Fetch candidates for a cell, score them, and return the passers.

    Does NOT change cell state or persist anything — the caller (probe_cycle)
    owns state transitions. Missing mapping card => no scoring context, treated
    as zero passers (the cell shouldn't have been enqueued without one, but we
    fail safe rather than crash).
    """
    adapter = adapter or HelpDocsAdapter()
    scorer = scorer or RelevanceScorer()

    # 1. What to search for (query expansion, #15).
    bundle = build_query_bundle(db, cell_id, competitor_id)
    # Route the bucket matching this adapter's source type to it.
    queries = getattr(bundle, adapter.source_type.value, []) or bundle.generic

    # 2. Raw candidates from the adapter (#17).
    candidates = adapter.fetch(cell_id, competitor_id, queries, limit=per_bucket_limit)

    # 3. Scoring context from the mapping card (#11 / #2).
    card = get_mapping_card_by_cell(db, cell_id)
    intent = card.intent_definition if card else ""
    inclusion = (card.inclusion_criteria if card else "") or ""
    exclusion = (card.exclusion_criteria if card else "") or ""

    # 4. Score each candidate (#19) and keep the passers.
    scored: list[tuple[Candidate, Score]] = []
    passed: list[tuple[Candidate, Score]] = []
    for cand in candidates:
        score = scorer.score(
            cand,
            intent_definition=intent,
            inclusion_criteria=inclusion,
            exclusion_criteria=exclusion,
        )
        scored.append((cand, score))
        if score.passed:
            passed.append((cand, score))

    # Highest score first — shortlist ordering (dedup/ranking refined in #20).
    passed.sort(key=lambda cs: cs[1].score, reverse=True)

    return ProbeResult(
        cell_id=cell_id,
        competitor_id=competitor_id,
        candidates_found=len(candidates),
        scored=scored,
        passed=passed,
    )
