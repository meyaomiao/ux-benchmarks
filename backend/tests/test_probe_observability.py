"""Unit tests for append-only M3 probe observability."""

from types import SimpleNamespace
from uuid import uuid4

from app.api.v1 import m3
from app.services.m3_collection.probe_observability import (
    ProbeTelemetry,
    list_probe_runs,
    log_probe_run,
    summarize_probe_runs,
)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _RowsResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _WriterSession:
    def __init__(self, project_id, *, commit_error=None, rollback_error=None):
        self.project_id = project_id
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, _statement):
        return _ScalarResult(self.project_id)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1
        if self.commit_error is not None:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_error is not None:
            raise self.rollback_error


def test_log_probe_run_persists_complete_cost_snapshot():
    project_id, cell_id, competitor_id = uuid4(), uuid4(), uuid4()
    db = _WriterSession(project_id)
    telemetry = ProbeTelemetry()
    telemetry.source_budgets = {"help_docs": {"max_searches": 2}}
    telemetry.source_stats = {
        "help_docs": {"search_calls": 2, "browser_pages": 1},
        "agentic_site": {"search_calls": 0, "browser_pages": 3},
    }
    telemetry.agentic_stats = {"model_calls": 4, "stop_reason": "model_stop"}
    telemetry.agentic_trace = [
        {"step": 1, "action": "save", "page_url": "https://example.com/"}
    ]
    telemetry.scoring_calls = 7
    telemetry.rescore_render_attempts = 2

    row = log_probe_run(
        db,
        cell_id,
        competitor_id,
        telemetry,
        probe_cycle=3,
        outcome="completed",
        final_state="SHORTLIST_READY",
        candidates_found=6,
        scored_count=7,
        passed_count=2,
        persisted_count=2,
    )

    assert row is db.added[0]
    assert db.commits == 1
    assert row.project_id == project_id
    assert row.candidates_found == 6
    assert row.scored_count == 7
    assert row.search_calls == 2
    assert row.browser_pages == 6
    assert row.scoring_calls == 7
    assert row.agentic_model_calls == 4
    assert row.agentic_trace == telemetry.agentic_trace
    assert row.finished_at == telemetry.finished_at
    assert row.duration_ms == telemetry.summary()["duration_ms"]


def test_log_probe_run_failure_never_escapes_even_when_rollback_fails():
    db = _WriterSession(
        uuid4(),
        commit_error=RuntimeError("insert failed"),
        rollback_error=RuntimeError("connection lost"),
    )

    row = log_probe_run(
        db,
        uuid4(),
        uuid4(),
        ProbeTelemetry(),
        probe_cycle=1,
        outcome="completed",
        final_state="REJECTED_EMPTY",
    )

    assert row is None
    assert db.commits == 1
    assert db.rollbacks == 1


class _QuerySession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _ScalarResult(len(self.rows))
        return _RowsResult(self.rows)


def test_list_probe_runs_applies_project_filters_and_pagination():
    project_id, cell_id, competitor_id = uuid4(), uuid4(), uuid4()
    expected = [SimpleNamespace(id=uuid4())]
    db = _QuerySession(expected)

    rows, total = list_probe_runs(
        db,
        project_id,
        limit=25,
        offset=50,
        cell_id=cell_id,
        competitor_id=competitor_id,
        strategy_version="strategy-v2",
    )

    assert rows == expected
    assert total == 1
    count_params = db.statements[0].compile().params.values()
    list_params = db.statements[1].compile().params.values()
    for expected_param in (project_id, cell_id, competitor_id, "strategy-v2"):
        assert expected_param in count_params
        assert expected_param in list_params
    assert 25 in list_params
    assert 50 in list_params


def test_summary_computes_effectiveness_and_separate_model_costs():
    aggregate = SimpleNamespace(
        strategy_version="strategy-v2",
        runs=4,
        runs_with_passers=2,
        candidates_found=20,
        scored_count=22,
        passed_count=5,
        persisted_count=4,
        avg_duration_ms=1250,
        avg_search_calls=3.5,
        avg_browser_pages=2.5,
        avg_scoring_calls=5.5,
        avg_agentic_model_calls=1.5,
        avg_model_calls=7.0,
    )

    class _SummarySession:
        def execute(self, _statement):
            return _RowsResult([aggregate])

    assert summarize_probe_runs(_SummarySession(), uuid4()) == [
        {
            "strategy_version": "strategy-v2",
            "runs": 4,
            "runs_with_passers": 2,
            "candidates_found": 20,
            "scored_count": 22,
            "passed_count": 5,
            "persisted_count": 4,
            "run_success_rate": 0.5,
            "candidate_pass_rate": 0.25,
            "candidate_persist_rate": 0.2,
            "avg_duration_ms": 1250.0,
            "avg_search_calls": 3.5,
            "avg_browser_pages": 2.5,
            "avg_scoring_calls": 5.5,
            "avg_agentic_model_calls": 1.5,
            "avg_model_calls": 7.0,
        }
    ]


def test_probe_run_api_forwards_project_scope_filters_and_pagination(monkeypatch):
    project_id, cell_id, competitor_id = uuid4(), uuid4(), uuid4()
    calls = []

    def fake_list(db, scoped_project_id, **kwargs):
        calls.append((db, scoped_project_id, kwargs))
        return [], 51

    monkeypatch.setattr(m3, "list_probe_runs", fake_list)
    db = object()

    response = m3.get_probe_runs(
        limit=25,
        offset=25,
        cell_id=cell_id,
        competitor_id=competitor_id,
        strategy_version="strategy-v2",
        db=db,
        project_id=project_id,
    )

    assert calls == [
        (
            db,
            project_id,
            {
                "limit": 25,
                "offset": 25,
                "cell_id": cell_id,
                "competitor_id": competitor_id,
                "strategy_version": "strategy-v2",
            },
        )
    ]
    assert response.total == 51
    assert response.has_next is True


def test_probe_run_summary_api_forwards_project_scope(monkeypatch):
    project_id = uuid4()
    calls = []
    monkeypatch.setattr(
        m3,
        "summarize_probe_runs",
        lambda db, scoped_project_id: calls.append((db, scoped_project_id)) or [],
    )
    db = object()

    assert m3.get_probe_run_summary(db=db, project_id=project_id) == []
    assert calls == [(db, project_id)]
