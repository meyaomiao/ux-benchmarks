"""Offline orchestration tests for run_probe_pipeline.

The pipeline's two DB calls (build_query_bundle, get_mapping_card_by_cell) are
monkeypatched so the fetch -> score -> keep-passers logic is exercised without a
database, using fake adapter/scorer that satisfy the contracts Protocols.
"""
from uuid import uuid4

import app.services.m3_collection.pipeline as pipeline_mod
from app.services.m3_collection.contracts import (
    Candidate,
    EvidenceType,
    RubricBreakdown,
    Score,
    SourceType,
)
from app.services.m3_collection.pipeline import run_probe_pipeline
from app.schemas.m3 import QueryBundle


class _FakeAdapter:
    source_type = SourceType.HELP_DOCS

    def __init__(self, n):
        self._n = n

    def fetch(self, cell_id, competitor_id, queries, *, limit=10):
        return [
            Candidate(
                cell_id=cell_id,
                competitor_id=competitor_id,
                source_url=f"https://help.example.com/{i}",
                source_type=self.source_type,
                text_content=f"doc {i}",
            )
            for i in range(self._n)
        ]


class _FakeScorer:
    """Scores candidate i as passing when i is even."""

    def score(self, candidate, **kwargs):
        # deterministic: even-indexed URLs pass
        idx = int(candidate.source_url.rsplit("/", 1)[-1])
        val = 0.9 if idx % 2 == 0 else 0.1
        return Score(
            candidate_id=candidate.candidate_id,
            score=val,
            passed=val >= 0.55,
            evidence_type=EvidenceType.OBSERVED,
            rubric=RubricBreakdown(state_match=val),
            reasoning="fake",
        )


def _patch_db(monkeypatch):
    monkeypatch.setattr(
        pipeline_mod, "build_query_bundle",
        lambda db, cell_id, competitor_id: QueryBundle(help_docs=["q1", "q2"]),
    )
    monkeypatch.setattr(
        pipeline_mod, "get_mapping_card_by_cell",
        lambda db, cell_id: None,  # no card => empty intent, fine for orchestration
    )


def test_pipeline_keeps_only_passers(monkeypatch):
    _patch_db(monkeypatch)
    result = run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(4), scorer=_FakeScorer(),
    )
    assert result.candidates_found == 4
    assert len(result.scored) == 4
    assert len(result.passed) == 2          # indexes 0 and 2
    assert result.has_passers is True


def test_pipeline_no_passers(monkeypatch):
    _patch_db(monkeypatch)

    class _AllFail(_FakeScorer):
        def score(self, candidate, **kwargs):
            s = super().score(candidate, **kwargs)
            return Score(
                candidate_id=s.candidate_id, score=0.1, passed=False,
                evidence_type=s.evidence_type, rubric=s.rubric, reasoning="fail",
            )

    result = run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(3), scorer=_AllFail(),
    )
    assert result.candidates_found == 3
    assert result.has_passers is False


def test_pipeline_passers_sorted_desc(monkeypatch):
    _patch_db(monkeypatch)
    result = run_probe_pipeline(
        db=None, cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(6), scorer=_FakeScorer(),
    )
    scores = [s.score for _, s in result.passed]
    assert scores == sorted(scores, reverse=True)
