"""DB-backed probe-queue orchestration for M3 collection.

Sits on top of coverage_state_service + state_machine. Handles enqueueing
(cell x competitor) pairs for probing, listing the current queue, and pulling
the next pair to probe.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.m5_coverage import CoverageSnapshot
from app.services.m3_collection.coverage_state_service import (
    enqueue,
    get_or_create_snapshot,
    transition_state,
)
from app.services.m3_collection.state_machine import CellState, Trigger


def enqueue_cell(
    db: Session, cell_id: UUID, competitor_id: UUID, trigger: str
) -> CoverageSnapshot:
    """Queue a (cell x competitor) pair for (re)probing.

    OPTION A (confirmed product decision — see issue #14 comment):
    a SATURATED snapshot cannot go straight to QUEUED per the state machine
    (SATURATED -> STALE -> QUEUED). When a user forces re-collection with a
    MANUAL_PIN, we do not want them to have to invalidate freshness first.
    So for trigger == MANUAL_PIN on a SATURATED snapshot we auto-route the two
    transitions (SATURATED -> STALE -> QUEUED) so one user action suffices.

    For all other eligible states we delegate to coverage_state_service.enqueue,
    which is a no-op (returns as-is) when the snapshot is already QUEUED/PROBING.
    """
    snapshot = get_or_create_snapshot(db, cell_id, competitor_id)

    # Already in-flight — nothing to do.
    if snapshot.status in (CellState.QUEUED, CellState.PROBING):
        return snapshot

    # OPTION A: manual force re-collection of a saturated cell.
    if (
        trigger == Trigger.MANUAL_PIN
        and snapshot.status == CellState.SATURATED
    ):
        transition_state(
            db, cell_id, competitor_id, CellState.STALE, note=trigger
        )
        return transition_state(
            db, cell_id, competitor_id, CellState.QUEUED, note=trigger
        )

    # All other eligible states: normal enqueue (no-op if not eligible).
    return enqueue(db, cell_id, competitor_id, trigger)


def list_queued(db: Session, limit: int = 50, project_id: UUID | None = None) -> list[CoverageSnapshot]:
    """Return QUEUED snapshots, oldest-probed first, scoped to a project.

    Actual priority ordering (see priority.py) is computed by the caller/worker
    because PriorityInputs need data assembled from multiple sources. For now we
    order by last_probed_at (nulls first — never-probed cells lead), then
    updated_at as a stable tie-breaker.
    """
    q = db.query(CoverageSnapshot).filter(CoverageSnapshot.status == CellState.QUEUED)
    if project_id is not None:
        q = q.filter(CoverageSnapshot.project_id == project_id)
    return (
        q.order_by(
            CoverageSnapshot.last_probed_at.asc().nullsfirst(),
            CoverageSnapshot.updated_at.asc(),
        )
        .limit(limit)
        .all()
    )


def dequeue_next(db: Session) -> CoverageSnapshot | None:
    """Pull the oldest QUEUED snapshot, transition it to PROBING, return it.

    FIFO placeholder until full priority assembly lands in a later issue.
    Returns None when the queue is empty.
    """
    queued = list_queued(db, limit=1)
    if not queued:
        return None
    snapshot = queued[0]
    return transition_state(
        db,
        snapshot.cell_id,
        snapshot.competitor_id,
        CellState.PROBING,
    )
