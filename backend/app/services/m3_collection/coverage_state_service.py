"""DB-backed helpers for driving the M3 collection state machine.

Operates on CoverageSnapshot rows (one per cell x competitor pair), applying
the transition rules defined in state_machine.py.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.m5_coverage import CoverageSnapshot
from app.services.m3_collection.state_machine import (
    CellState,
    assert_transition,
    can_transition,
)


def get_or_create_snapshot(
    db: Session, cell_id: UUID, competitor_id: UUID
) -> CoverageSnapshot:
    """Return the snapshot for the pair, creating an UNPROBED one if missing."""
    snapshot = (
        db.query(CoverageSnapshot)
        .filter(
            CoverageSnapshot.cell_id == cell_id,
            CoverageSnapshot.competitor_id == competitor_id,
        )
        .one_or_none()
    )
    if snapshot is None:
        snapshot = CoverageSnapshot(
            cell_id=cell_id,
            competitor_id=competitor_id,
            status=CellState.UNPROBED,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
    return snapshot


def transition_state(
    db: Session,
    cell_id: UUID,
    competitor_id: UUID,
    to_state: str,
    *,
    note: str | None = None,
) -> CoverageSnapshot:
    """Move the pair's snapshot to `to_state`, validating the transition.

    Raises AppError("INVALID_TRANSITION", ...) if the move is not allowed.
    Entering PROBING bumps probe_cycles and stamps last_probed_at.
    """
    snapshot = get_or_create_snapshot(db, cell_id, competitor_id)
    assert_transition(snapshot.status, to_state)
    snapshot.status = to_state
    if to_state == CellState.PROBING:
        snapshot.probe_cycles = (snapshot.probe_cycles or 0) + 1
        snapshot.last_probed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def enqueue(
    db: Session, cell_id: UUID, competitor_id: UUID, trigger: str
) -> CoverageSnapshot:
    """Queue the pair for (re)probing.

    Valid from UNPROBED / PARTIAL / REJECTED_EMPTY / STALE. If the snapshot is
    already QUEUED or PROBING, this is a no-op and the snapshot is returned as-is.
    """
    snapshot = get_or_create_snapshot(db, cell_id, competitor_id)
    if not can_transition(snapshot.status, CellState.QUEUED):
        # Already QUEUED/PROBING (or otherwise not eligible) -> no-op.
        return snapshot
    return transition_state(
        db, cell_id, competitor_id, CellState.QUEUED, note=trigger
    )
