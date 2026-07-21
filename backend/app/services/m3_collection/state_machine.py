"""M3 cell collection state machine.

Collection state is tracked per (cell x competitor) pair and persisted on
CoverageSnapshot.status. This module encodes the states, triggers, and the
allowed transitions between states. Pure logic only, no DB access.
"""
from enum import StrEnum

from app.core.errors import AppError


class CellState(StrEnum):
    UNPROBED = "UNPROBED"
    QUEUED = "QUEUED"
    PROBING = "PROBING"
    SHORTLIST_READY = "SHORTLIST_READY"
    PARTIAL = "PARTIAL"
    SATURATED = "SATURATED"
    REJECTED_EMPTY = "REJECTED_EMPTY"
    STALE = "STALE"


class Trigger(StrEnum):
    NEW_CELL = "NEW_CELL"
    COVERAGE_GAP = "COVERAGE_GAP"
    FRESHNESS_DECAY = "FRESHNESS_DECAY"
    UPSTREAM_INVALIDATION = "UPSTREAM_INVALIDATION"
    MANUAL_PIN = "MANUAL_PIN"
    CONTRADICTION = "CONTRADICTION"


ALLOWED_TRANSITIONS: dict[CellState, set[CellState]] = {
    CellState.UNPROBED: {CellState.QUEUED},
    CellState.QUEUED: {CellState.PROBING},
    CellState.PROBING: {CellState.SHORTLIST_READY, CellState.REJECTED_EMPTY},
    CellState.SHORTLIST_READY: {
        CellState.PARTIAL,
        CellState.SATURATED,
        CellState.REJECTED_EMPTY,
    },
    CellState.PARTIAL: {CellState.QUEUED, CellState.SATURATED},
    CellState.SATURATED: {CellState.STALE},
    CellState.REJECTED_EMPTY: {CellState.QUEUED},
    CellState.STALE: {CellState.QUEUED},
}


def can_transition(frm: str, to: str) -> bool:
    """Return True if moving from state `frm` to state `to` is allowed.

    Unknown states (values not present in ALLOWED_TRANSITIONS) yield False.
    """
    try:
        frm_state = CellState(frm)
        to_state = CellState(to)
    except ValueError:
        return False
    return to_state in ALLOWED_TRANSITIONS.get(frm_state, set())


def assert_transition(frm: str, to: str) -> None:
    """Raise AppError if the transition from `frm` to `to` is not allowed."""
    if not can_transition(frm, to):
        raise AppError("INVALID_TRANSITION", f"{frm} -> {to} not allowed", 409)
