"""Unit tests for M3 queue-service requeue behavior."""

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
