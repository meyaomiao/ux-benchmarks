"""Queue-isolation tests for the manual probe API."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from celery.exceptions import OperationalError, TimeLimitExceeded
from celery.exceptions import TimeoutError as CeleryTimeoutError

from app.api.v1 import m3
from app.core.errors import AppError
from app.services.m3_collection.state_machine import CellState, Trigger


class _Result:
    def __init__(self, value=None, error=None):
        self.value = value
        self.error = error
        self.get_calls = []

    def get(self, *, timeout, propagate):
        self.get_calls.append((timeout, propagate))
        if self.error is not None:
            raise self.error
        return self.value


def _payload(cell_id, competitor_id):
    return {
        "status": "done",
        "cell_id": str(cell_id),
        "competitor_id": str(competitor_id),
        "state": CellState.SHORTLIST_READY,
        "probe_cycles": 2,
        "candidates_found": 3,
        "passed": 1,
        "persisted": 1,
        "agentic_stats": {"pages_opened": 2},
    }


def _wire_queued(monkeypatch, result):
    enqueue_calls = []
    dispatch_calls = []

    def enqueue(db, cell_id, competitor_id, trigger):
        enqueue_calls.append((db, cell_id, competitor_id, trigger))
        return SimpleNamespace(status=CellState.QUEUED)

    def dispatch(*, args, queue):
        dispatch_calls.append((args, queue))
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(m3, "enqueue_cell", enqueue)
    monkeypatch.setattr(m3.run_probe_cycle, "apply_async", dispatch)
    return enqueue_calls, dispatch_calls


@pytest.mark.asyncio
async def test_dispatch_queued_explicitly_targets_browser_queue(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    row = SimpleNamespace(cell_id=cell_id, competitor_id=competitor_id)
    query_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [row])
    )
    db = SimpleNamespace(execute=lambda _query: query_result)
    dispatch_calls = []

    monkeypatch.setattr(
        m3.run_probe_cycle,
        "apply_async",
        lambda *, args, queue: dispatch_calls.append((args, queue)),
    )

    result = await m3.dispatch_queued(db=db, project_id=uuid4())

    assert result == {"dispatched": 1}
    assert dispatch_calls == [((str(cell_id), str(competitor_id)), "browser")]


def test_probe_now_enqueues_browser_task_and_preserves_response(monkeypatch):
    cell_id, competitor_id = uuid4(), uuid4()
    expected = _payload(cell_id, competitor_id)
    task_result = _Result(expected)
    enqueue_calls, dispatch_calls = _wire_queued(monkeypatch, task_result)
    db = object()

    actual = m3.probe_now(
        {"cell_id": str(cell_id), "competitor_id": str(competitor_id)},
        db=db,
    )

    assert actual == expected
    assert enqueue_calls == [(db, cell_id, competitor_id, Trigger.MANUAL_PIN)]
    assert dispatch_calls == [((str(cell_id), str(competitor_id)), "browser")]
    assert task_result.get_calls == [(m3.PROBE_NOW_RESULT_TIMEOUT, True)]


def test_probe_now_rejects_pair_already_probing_without_dispatch(monkeypatch):
    monkeypatch.setattr(
        m3,
        "enqueue_cell",
        lambda *_args: SimpleNamespace(status=CellState.PROBING),
    )
    monkeypatch.setattr(
        m3.run_probe_cycle,
        "apply_async",
        lambda **_kwargs: pytest.fail("PROBING pair must not dispatch another task"),
    )

    with pytest.raises(AppError) as exc:
        m3.probe_now(
            {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
            db=object(),
        )

    assert (exc.value.code, exc.value.status_code) == ("PROBE_ALREADY_RUNNING", 409)


def test_probe_now_reports_broker_failure_without_empty_result(monkeypatch):
    _wire_queued(monkeypatch, OSError("broker unavailable"))

    with pytest.raises(AppError) as exc:
        m3.probe_now(
            {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
            db=object(),
        )

    assert (exc.value.code, exc.value.status_code) == ("PROBE_DISPATCH_FAILED", 503)


def test_probe_now_reports_queue_wait_timeout_without_empty_result(monkeypatch):
    _wire_queued(monkeypatch, _Result(error=CeleryTimeoutError()))

    with pytest.raises(AppError) as exc:
        m3.probe_now(
            {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
            db=object(),
        )

    assert (exc.value.code, exc.value.status_code) == ("PROBE_WAIT_TIMEOUT", 504)


@pytest.mark.parametrize("status", ["timeout", "recovered"])
def test_probe_now_reports_worker_timeout_status(monkeypatch, status):
    _wire_queued(
        monkeypatch,
        _Result({"status": status, "state": CellState.REJECTED_EMPTY}),
    )

    with pytest.raises(AppError) as exc:
        m3.probe_now(
            {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
            db=object(),
        )

    assert (exc.value.code, exc.value.status_code) == ("PROBE_EXECUTION_TIMEOUT", 504)


def test_probe_now_reports_worker_failure(monkeypatch):
    _wire_queued(monkeypatch, _Result(error=RuntimeError("browser crashed")))

    with pytest.raises(AppError) as exc:
        m3.probe_now(
            {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
            db=object(),
        )

    assert (exc.value.code, exc.value.status_code) == ("PROBE_EXECUTION_FAILED", 502)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeLimitExceeded(14 * 60), ("PROBE_EXECUTION_TIMEOUT", 504)),
        (OperationalError("result backend unavailable"), ("PROBE_RESULT_UNAVAILABLE", 503)),
    ],
)
def test_probe_now_distinguishes_hard_timeout_and_result_backend_failure(
    monkeypatch, error, expected
):
    _wire_queued(monkeypatch, _Result(error=error))

    with pytest.raises(AppError) as exc:
        m3.probe_now(
            {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
            db=object(),
        )

    assert (exc.value.code, exc.value.status_code) == expected


def test_probe_now_rejects_skipped_or_incomplete_task_results(monkeypatch):
    for result, expected in [
        ({"status": "skipped", "state": CellState.PROBING}, ("PROBE_ALREADY_RUNNING", 409)),
        ({"status": "done", "state": CellState.SHORTLIST_READY}, ("PROBE_INVALID_RESULT", 502)),
    ]:
        _wire_queued(monkeypatch, _Result(result))
        with pytest.raises(AppError) as exc:
            m3.probe_now(
                {"cell_id": str(uuid4()), "competitor_id": str(uuid4())},
                db=object(),
            )
        assert (exc.value.code, exc.value.status_code) == expected
