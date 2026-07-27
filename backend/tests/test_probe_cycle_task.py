"""Focused guardrail tests for the Celery probe task."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from celery.exceptions import TimeLimitExceeded
from celery.worker import request as celery_request
from kombu.transport.redis import Channel as RedisChannel

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
    assert celery_app.conf.task_acks_on_failure_or_timeout is True
    assert probe_cycle.run_probe_cycle.acks_on_failure_or_timeout is False
    assert celery_app.conf.task_routes["app.workers.tasks.probe_cycle.*"] == {
        "queue": "browser"
    }
    assert celery_app.amqp.router.route({}, probe_cycle.run_probe_cycle.name)["queue"].name == (
        "browser"
    )


def test_hard_timeout_callback_does_not_ack_probe_task(monkeypatch):
    decisions = []
    failures = []
    monkeypatch.setattr(celery_request, "task_ready", lambda _request: None)
    monkeypatch.setattr(celery_request.state, "should_terminate", False)
    monkeypatch.setattr(
        probe_cycle.run_probe_cycle,
        "_backend",
        SimpleNamespace(
            mark_as_failure=lambda *args, **kwargs: failures.append((args, kwargs))
        ),
    )
    request = SimpleNamespace(
        task=probe_cycle.run_probe_cycle,
        name=probe_cycle.run_probe_cycle.name,
        id="probe-hard-timeout",
        _context={},
        store_errors=False,
        acknowledge=lambda: decisions.append("ack"),
    )

    celery_request.Request.on_timeout(
        request, soft=False, timeout=probe_cycle.PROBE_HARD_TIME_LIMIT
    )

    assert failures
    assert decisions == []


def _celery_failure_decision(monkeypatch, exception):
    decisions = []
    request = SimpleNamespace(
        task=probe_cycle.run_probe_cycle,
        acknowledge=lambda: decisions.append(("ack", None)),
        reject=lambda requeue=False: decisions.append(("reject", requeue)),
    )
    monkeypatch.setattr(celery_request, "task_ready", lambda _request: None)
    monkeypatch.setattr(celery_request.state, "should_terminate", False)

    celery_request.Request.on_failure(
        request,
        SimpleNamespace(exception=exception),
        send_failed_event=False,
        return_ok=True,
    )
    return decisions


def test_hard_timeout_is_requeued_by_current_celery(monkeypatch):
    decisions = _celery_failure_decision(
        monkeypatch, TimeLimitExceeded(probe_cycle.PROBE_HARD_TIME_LIMIT)
    )

    assert decisions == [("reject", True)]


def test_ordinary_failure_is_rejected_without_requeue(monkeypatch):
    decisions = _celery_failure_decision(
        monkeypatch, RuntimeError("browser disconnected")
    )

    assert decisions == [("reject", False)]


def test_redis_restore_sets_redelivery_flag_read_by_probe_task():
    payload = {"headers": {}, "properties": {"delivery_info": {}}}
    restored = []
    channel = SimpleNamespace(
        _lookup=lambda _exchange, _routing_key: ["adapters"],
        _get_message_priority=lambda _payload, reverse=False: 0,
        _q_for_pri=lambda queue, _priority: queue,
    )
    pipe = SimpleNamespace(
        lpush=lambda queue, message: restored.append((queue, message)),
        rpush=lambda queue, message: restored.append((queue, message)),
    )

    RedisChannel._do_restore_message(
        channel, payload, "", "adapters", pipe, leftmost=True
    )

    assert restored
    assert payload["properties"]["delivery_info"]["redelivered"] is True
    task = SimpleNamespace(
        request=SimpleNamespace(
            delivery_info=payload["properties"]["delivery_info"]
        )
    )
    assert probe_cycle._is_redelivered(task) is True


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


def test_browser_queue_task_runs_probe_inline_without_nested_celery_wait(monkeypatch):
    db, _snapshot, transitions = _wire_state(monkeypatch, CellState.QUEUED)
    cell_id, competitor_id = uuid4(), uuid4()
    calls = []

    def probe(got_db, got_cell_id, got_competitor_id):
        calls.append((got_db, got_cell_id, got_competitor_id))
        return {
            "candidates_found": 2,
            "passed": 1,
            "state": CellState.SHORTLIST_READY,
        }

    monkeypatch.setattr(probe_cycle, "run_probe", probe)

    out = probe_cycle.run_probe_cycle.run(str(cell_id), str(competitor_id))

    assert calls == [(db, cell_id, competitor_id)]
    assert out == {
        "status": "done",
        "candidates_found": 2,
        "passed": 1,
        "state": CellState.SHORTLIST_READY,
    }
    assert transitions == []
    assert db.closed is True


def test_soft_timeout_cleanup_is_idempotent_after_runner_transition(monkeypatch):
    db, snapshot, transitions = _wire_state(monkeypatch, CellState.QUEUED)

    def timeout_after_transition(*_args):
        snapshot.status = CellState.REJECTED_EMPTY
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(probe_cycle, "run_probe", timeout_after_transition)

    out = probe_cycle.run_probe_cycle.run(str(uuid4()), str(uuid4()))

    assert out == {
        "status": "timeout",
        "state": CellState.REJECTED_EMPTY,
        "error": "soft time limit exceeded",
    }
    assert transitions == []
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
