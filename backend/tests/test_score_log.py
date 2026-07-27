"""Unit tests for the probe score-log writer (diagnostics, best-effort)."""

from types import SimpleNamespace
from uuid import uuid4

from app.services.m3_collection import score_log
from app.services.m3_collection.contracts import (
    Candidate,
    EvidenceType,
    RubricBreakdown,
    Score,
    SourceType,
)


class _FakeDB:
    def __init__(self, *, project_id=None, raise_on_execute=False):
        self.project_id = project_id
        self.raise_on_execute = raise_on_execute
        self.added: list = []
        self.committed = False
        self.rolled_back = False

    def execute(self, _stmt):
        if self.raise_on_execute:
            raise RuntimeError("relation \"grid_cells\" does not exist")
        return SimpleNamespace(scalar_one=lambda: self.project_id)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _pair(cell_id, competitor_id, *, score: float, passed: bool, image=None):
    candidate = Candidate(
        cell_id=cell_id,
        competitor_id=competitor_id,
        source_url="https://example.com/help/x",
        source_type=SourceType.HELP_DOCS,
        image_path=image,
    )
    return candidate, Score(
        candidate_id=candidate.candidate_id,
        score=score,
        passed=passed,
        evidence_type=EvidenceType.OBSERVED,
        rubric=RubricBreakdown(state_match=0.6, product_match=0.7),
        reasoning="r" * 3000,
        scored_by="gpt:gpt-5.6-luna",
    )


def test_logs_rejected_candidates_too():
    cell_id, competitor_id, project_id = uuid4(), uuid4(), uuid4()
    db = _FakeDB(project_id=project_id)
    scored = [
        _pair(cell_id, competitor_id, score=0.81, passed=True, image="/tmp/a.png"),
        _pair(cell_id, competitor_id, score=0.12, passed=False),
    ]

    assert score_log.log_scored_candidates(
        db, cell_id, competitor_id, scored, probe_cycle=3
    ) == 2
    assert db.committed
    assert [row.passed for row in db.added] == [True, False]
    assert [row.score for row in db.added] == [0.81, 0.12]
    assert [row.has_image for row in db.added] == [True, False]

    row = db.added[0]
    assert row.project_id == project_id
    assert row.probe_cycle == 3
    assert row.source_type == SourceType.HELP_DOCS.value
    assert row.evidence_type == EvidenceType.OBSERVED.value
    assert row.score_breakdown["state_match"] == 0.6
    assert len(row.reasoning) == score_log._REASONING_MAX


def test_empty_input_is_a_noop():
    db = _FakeDB(project_id=uuid4())
    assert score_log.log_scored_candidates(db, uuid4(), uuid4(), []) == 0
    assert not db.committed
    assert db.added == []


def test_failure_is_swallowed_so_the_probe_survives():
    cell_id, competitor_id = uuid4(), uuid4()
    db = _FakeDB(raise_on_execute=True)
    scored = [_pair(cell_id, competitor_id, score=0.4, passed=False)]

    assert score_log.log_scored_candidates(db, cell_id, competitor_id, scored) == 0
    assert db.rolled_back
    assert not db.committed
