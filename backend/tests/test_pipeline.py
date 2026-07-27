"""Offline orchestration tests for run_probe_pipeline.

The pipeline's two DB calls (build_query_bundle, get_mapping_card_by_cell) are
monkeypatched so the fetch -> score -> keep-passers logic is exercised without a
database, using fake adapter/scorer that satisfy the contracts Protocols.
"""
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

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


def test_pipeline_does_not_swallow_soft_timeout(monkeypatch):
    _patch_db(monkeypatch)

    class _TimedOutAdapter(_FakeAdapter):
        def fetch(self, *_args, **_kwargs):
            raise SoftTimeLimitExceeded()

    with pytest.raises(SoftTimeLimitExceeded):
        run_probe_pipeline(
            db=None,
            cell_id=uuid4(),
            competitor_id=uuid4(),
            adapter=_TimedOutAdapter(0),
            scorer=_FakeScorer(),
        )


class _CaptureScorer:
    """Records the scoring context handed to the scorer."""

    def __init__(self):
        self.kwargs = None

    def score(self, candidate, **kwargs):
        self.kwargs = kwargs
        return Score(
            candidate_id=candidate.candidate_id,
            score=0.9, passed=True,
            evidence_type=EvidenceType.OBSERVED,
            rubric=RubricBreakdown(state_match=0.9),
            reasoning="capture",
        )


class _FakeCard:
    intent_definition = "用户在风险高亮态审查合同条款"
    inclusion_criteria = "必须出现合同风险标记"
    exclusion_criteria = "排除营销页"


class _FakeComp:
    canonical_name = "Vercel"

    def __init__(self, competitor_type):
        self.competitor_type = competitor_type


class _FakeCell:
    page_state = "风险高亮态"
    journey_stage = "日常审查"
    jtbd = "查看AI提取的条款与风险标记"


class _FakeDB:
    """Returns the competitor first, then the grid cell — the pipeline's order."""

    def __init__(self, competitor_type):
        self._rows = [_FakeComp(competitor_type), _FakeCell()]

    def execute(self, _stmt):
        row = self._rows.pop(0) if self._rows else None

        class _Res:
            def scalar_one_or_none(self_inner):
                return row

        return _Res()


def _patch_context(monkeypatch, pattern="side-by-side diff review"):
    monkeypatch.setattr(
        pipeline_mod, "build_query_bundle",
        lambda db, cell_id, competitor_id: QueryBundle(help_docs=["q1"]),
    )
    monkeypatch.setattr(
        pipeline_mod, "get_mapping_card_by_cell", lambda db, cell_id: _FakeCard(),
    )
    monkeypatch.setattr(
        pipeline_mod, "abstract_interaction_pattern",
        lambda page_state, journey_stage, jtbd="": pattern,
    )
    # Keep these tests offline: live mode would resolve query strings through the
    # real search API before the fake adapter ever runs.
    monkeypatch.setattr(
        pipeline_mod, "resolve_queries_to_urls",
        lambda queries, max_total=0: list(queries),
    )


def test_cross_industry_pair_is_scored_on_interaction_pattern(monkeypatch):
    _patch_context(monkeypatch)
    scorer = _CaptureScorer()
    run_probe_pipeline(
        db=_FakeDB("cross_industry"), cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(1), scorer=scorer,
    )
    assert scorer.kwargs["intent_definition"].startswith("side-by-side diff review")
    # Domain-language criteria would re-impose the filter the pattern removed.
    assert scorer.kwargs["inclusion_criteria"] == ""
    assert scorer.kwargs["exclusion_criteria"] == ""
    assert scorer.kwargs["product_name"] == "Vercel"


def test_direct_pair_keeps_domain_context(monkeypatch):
    _patch_context(monkeypatch)
    scorer = _CaptureScorer()
    run_probe_pipeline(
        db=_FakeDB("direct"), cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(1), scorer=scorer,
    )
    assert scorer.kwargs["intent_definition"] == _FakeCard.intent_definition
    assert scorer.kwargs["inclusion_criteria"] == _FakeCard.inclusion_criteria
    assert scorer.kwargs["exclusion_criteria"] == _FakeCard.exclusion_criteria


def test_unavailable_abstraction_falls_back_to_domain_context(monkeypatch):
    _patch_context(monkeypatch, pattern="")
    scorer = _CaptureScorer()
    run_probe_pipeline(
        db=_FakeDB("indirect"), cell_id=uuid4(), competitor_id=uuid4(),
        adapter=_FakeAdapter(1), scorer=scorer,
    )
    assert scorer.kwargs["intent_definition"] == _FakeCard.intent_definition
    assert scorer.kwargs["inclusion_criteria"] == _FakeCard.inclusion_criteria
