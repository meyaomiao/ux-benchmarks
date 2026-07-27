"""Unit tests for M3 queue-service requeue behavior."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.m3_collection import queue_service
from app.services.m3_collection.state_machine import CellState, Trigger


def _snapshot(status: CellState) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def test_manual_pin_requeues_shortlist_ready_via_partial(monkeypatch):
    snapshot = _snapshot(CellState.SHORTLIST_READY)
    calls: list[tuple[CellState, Trigger]] = []

    monkeypatch.setattr(queue_service, "get_or_create_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(
        queue_service,
        "enqueue",
        lambda *_: pytest.fail("SHORTLIST_READY manual pin should not delegate to enqueue"),
    )

    def fake_transition(_db, _cell_id, _competitor_id, to_state, *, note=None):
        calls.append((to_state, note))
        snapshot.status = to_state
        return snapshot

    monkeypatch.setattr(queue_service, "transition_state", fake_transition)

    result = queue_service.enqueue_cell(
        object(), uuid4(), uuid4(), Trigger.MANUAL_PIN
    )

    assert result is snapshot
    assert result.status == CellState.QUEUED
    assert calls == [
        (CellState.PARTIAL, Trigger.MANUAL_PIN),
        (CellState.QUEUED, Trigger.MANUAL_PIN),
    ]


def test_shortlist_ready_non_manual_pin_stays_noop(monkeypatch):
    snapshot = _snapshot(CellState.SHORTLIST_READY)
    calls: list[Trigger] = []

    monkeypatch.setattr(queue_service, "get_or_create_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(
        queue_service,
        "transition_state",
        lambda *_args, **_kwargs: pytest.fail("non-manual SHORTLIST_READY should not transition"),
    )

    def fake_enqueue(_db, _cell_id, _competitor_id, trigger):
        calls.append(trigger)
        return snapshot

    monkeypatch.setattr(queue_service, "enqueue", fake_enqueue)

    result = queue_service.enqueue_cell(
        object(), uuid4(), uuid4(), Trigger.COVERAGE_GAP
    )

    assert result is snapshot
    assert result.status == CellState.SHORTLIST_READY
    assert calls == [Trigger.COVERAGE_GAP]


@pytest.mark.parametrize("status", [CellState.QUEUED, CellState.PROBING])
def test_queued_and_probing_still_short_circuit(monkeypatch, status):
    snapshot = _snapshot(status)

    monkeypatch.setattr(queue_service, "get_or_create_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(
        queue_service,
        "transition_state",
        lambda *_args, **_kwargs: pytest.fail("in-flight snapshots should short-circuit"),
    )
    monkeypatch.setattr(
        queue_service,
        "enqueue",
        lambda *_: pytest.fail("in-flight snapshots should short-circuit"),
    )

    result = queue_service.enqueue_cell(
        object(), uuid4(), uuid4(), Trigger.MANUAL_PIN
    )

    assert result is snapshot
    assert result.status == status


def test_manual_pin_requeues_saturated_via_stale(monkeypatch):
    snapshot = _snapshot(CellState.SATURATED)
    calls: list[tuple[CellState, Trigger]] = []

    monkeypatch.setattr(queue_service, "get_or_create_snapshot", lambda *_: snapshot)
    monkeypatch.setattr(
        queue_service,
        "enqueue",
        lambda *_: pytest.fail("SATURATED manual pin should not delegate to enqueue"),
    )

    def fake_transition(_db, _cell_id, _competitor_id, to_state, *, note=None):
        calls.append((to_state, note))
        snapshot.status = to_state
        return snapshot

    monkeypatch.setattr(queue_service, "transition_state", fake_transition)

    result = queue_service.enqueue_cell(
        object(), uuid4(), uuid4(), Trigger.MANUAL_PIN
    )

    assert result is snapshot
    assert result.status == CellState.QUEUED
    assert calls == [
        (CellState.STALE, Trigger.MANUAL_PIN),
        (CellState.QUEUED, Trigger.MANUAL_PIN),
    ]


# --- reclaim_stuck_probing --------------------------------------------------


class _FakeQuery:
    """Records the criteria it was filtered by and returns canned rows."""

    def __init__(self, rows):
        self.rows = rows
        self.criteria: list = []

    def filter(self, *criteria):
        self.criteria.extend(criteria)
        return self

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, rows):
        self.fake_query = _FakeQuery(rows)

    def query(self, _model):
        return self.fake_query


def _probing_row() -> SimpleNamespace:
    return SimpleNamespace(
        status=CellState.PROBING,
        cell_id=uuid4(),
        competitor_id=uuid4(),
    )


def test_reclaim_stuck_probing_releases_each_row(monkeypatch):
    rows = [_probing_row(), _probing_row()]
    db = _FakeDB(rows)
    calls: list[tuple] = []

    def fake_transition(_db, cell_id, competitor_id, to_state, *, note=None):
        calls.append((cell_id, competitor_id, to_state))
        return SimpleNamespace(status=to_state)

    monkeypatch.setattr(queue_service, "transition_state", fake_transition)

    assert queue_service.reclaim_stuck_probing(db) == 2
    assert calls == [
        (rows[0].cell_id, rows[0].competitor_id, CellState.REJECTED_EMPTY),
        (rows[1].cell_id, rows[1].competitor_id, CellState.REJECTED_EMPTY),
    ]


def test_reclaim_stuck_probing_uses_older_than_as_cutoff(monkeypatch):
    db = _FakeDB([])
    monkeypatch.setattr(
        queue_service,
        "transition_state",
        lambda *_args, **_kwargs: pytest.fail("nothing stuck -> no transition"),
    )

    older_than = timedelta(minutes=30)
    before = datetime.now(timezone.utc)
    assert queue_service.reclaim_stuck_probing(db, older_than=older_than) == 0
    after = datetime.now(timezone.utc)

    cutoff = db.fake_query.criteria[1].right.value
    assert before - older_than <= cutoff <= after - older_than


def test_reclaim_stuck_probing_scopes_to_project(monkeypatch):
    monkeypatch.setattr(
        queue_service, "transition_state", lambda *_args, **_kwargs: None
    )

    unscoped = _FakeDB([])
    queue_service.reclaim_stuck_probing(unscoped)

    scoped = _FakeDB([])
    queue_service.reclaim_stuck_probing(scoped, uuid4())

    assert len(scoped.fake_query.criteria) == len(unscoped.fake_query.criteria) + 1
