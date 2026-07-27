"""Focused guardrail tests for the Celery probe task."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded

from app.services.m3_collection.state_machine import CellState
from app.workers.celery_app import celery_app
from app.workers.tasks import probe_cycle


class _FakeDB:
    def __init__(self):
        self.closed = False
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _wire_state(monkeypatch, initial_status):
    db = _FakeDB()
    snapshot = SimpleNamespace(status=initial_status, probe_cycles=1)
    transitions = []

    monkeypatch.setattr(probe_cycle, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        probe_cycle,
        "get_or_create_snapshot",
        lambda _db, _cell_id, _competitor_id: snapshot,
    )

    def fake_transition(_db, _cell_id, _competitor_id, to_state, *, note=None):
        snapshot.status = to_state
        transitions.append((to_state, note))
        return snapshot

    monkeypatch.setattr(probe_cycle, "transition_state", fake_transition)
    return db, snapshot, transitions


def test_probe_task_has_explicit_time_and_worker_guards():
    assert probe_cycle.run_probe_cycle.soft_time_limit == probe_cycle.PROBE_SOFT_TIME_LIMIT
    assert probe_cycle.run_probe_cycle.time_limit == probe_cycle.PROBE_HARD_TIME_LIMIT
    assert probe_cycle.PROBE_HARD_TIME_LIMIT > probe_cycle.PROBE_SOFT_TIME_LIMIT
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_soft_timeout_finishes_probing(monkeypatch):
    db, snapshot, transitions = _wire_state(monkeypatch, CellState.QUEUED)

    def timeout(*_args):
        snapshot.status = CellState.PROBING
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(probe_cycle, "run_probe", timeout)

    out = probe_cycle.run_probe_cycle.run(str(uuid4()), str(uuid4()))

    assert out["status"] == "timeout"
    assert snapshot.status == CellState.REJECTED_EMPTY
    assert transitions == [
        (CellState.REJECTED_EMPTY, "probe-cycle: soft time limit exceeded")
    ]
    assert db.rollbacks == 1
    assert db.closed is True


def test_unexpected_browser_error_finishes_probing_and_reraises(monkeypatch):
    db, snapshot, transitions = _wire_state(monkeypatch, CellState.QUEUED)

    def browser_error(*_args):
        snapshot.status = CellState.PROBING
        raise RuntimeError("browser disconnected")

    monkeypatch.setattr(probe_cycle, "run_probe", browser_error)

    with pytest.raises(RuntimeError, match="browser disconnected"):
        probe_cycle.run_probe_cycle.run(str(uuid4()), str(uuid4()))

    assert snapshot.status == CellState.REJECTED_EMPTY
    assert transitions == [(CellState.REJECTED_EMPTY, "probe-cycle: task failure")]
    assert db.rollbacks == 1
    assert db.closed is True


def test_redelivered_hard_timeout_recovers_probing(monkeypatch):
    db, snapshot, transitions = _wire_state(monkeypatch, CellState.PROBING)
    monkeypatch.setattr(probe_cycle, "_is_redelivered", lambda _task: True)
    monkeypatch.setattr(
        probe_cycle,
        "run_probe",
        lambda *_args: pytest.fail("redelivery must not start a second probe"),
    )

    out = probe_cycle.run_probe_cycle.run(str(uuid4()), str(uuid4()))

    assert out == {"status": "recovered", "state": CellState.REJECTED_EMPTY}
    assert transitions == [
        (
            CellState.REJECTED_EMPTY,
            "probe-cycle: recovered after worker hard timeout",
        )
    ]
    assert db.rollbacks == 1
    assert db.closed is True


def test_non_redelivered_probing_is_not_reclaimed(monkeypatch):
    db, _snapshot, transitions = _wire_state(monkeypatch, CellState.PROBING)
    monkeypatch.setattr(probe_cycle, "_is_redelivered", lambda _task: False)
    monkeypatch.setattr(
        probe_cycle,
        "run_probe",
        lambda *_args: pytest.fail("concurrent duplicate must be skipped"),
    )

    out = probe_cycle.run_probe_cycle.run(str(uuid4()), str(uuid4()))

    assert out == {"status": "skipped", "state": CellState.PROBING}
    assert transitions == []
    assert db.rollbacks == 0
    assert db.closed is True
