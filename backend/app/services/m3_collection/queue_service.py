"""DB-backed probe-queue orchestration for M3 collection.

Sits on top of coverage_state_service + state_machine. Handles enqueueing
(cell x competitor) pairs for probing, listing the current queue, and pulling
the next pair to probe.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.m5_coverage import CoverageSnapshot
from app.services.m3_collection.coverage_state_service import (
    enqueue,
    get_or_create_snapshot,
    transition_state,
)
from app.services.m3_collection.state_machine import CellState, Trigger

# A probe that has been PROBING longer than this is treated as dead: the worker
# or request that owned it is gone, and nothing else will ever move it on. Set
# well above the slowest observed probe (~12 min serial) so a slow-but-alive run
# is never reclaimed out from under itself.
STUCK_PROBING_AFTER = timedelta(hours=2)


def enqueue_cell(
    db: Session, cell_id: UUID, competitor_id: UUID, trigger: str
) -> CoverageSnapshot:
    """Queue a (cell x competitor) pair for (re)probing.

    OPTION A (confirmed product decision — see issue #14 comment):
    some states cannot go straight to QUEUED per the state machine. When a user
    forces re-collection with a MANUAL_PIN, we do not want them to have to
    perform an intermediate step first. So we auto-route the legal two-hop path
    for the specific MANUAL_PIN states that need it:

      - SATURATED -> STALE -> QUEUED
      - SHORTLIST_READY -> PARTIAL -> QUEUED

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

    if (
        trigger == Trigger.MANUAL_PIN
        and snapshot.status == CellState.SHORTLIST_READY
    ):
        transition_state(
            db, cell_id, competitor_id, CellState.PARTIAL, note=trigger
        )
        return transition_state(
            db, cell_id, competitor_id, CellState.QUEUED, note=trigger
        )

    # All other eligible states: normal enqueue (no-op if not eligible).
    return enqueue(db, cell_id, competitor_id, trigger)


def list_queued(
    db: Session, limit: int = 50, project_id: UUID | None = None
) -> list[CoverageSnapshot]:
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


def stop_queued(db: Session, project_id: UUID) -> int:
    """Cancel pending collection: reset all QUEUED pairs → UNPROBED for a project.

    Cooperative cancel — the probe task checks status at start and skips anything
    no longer QUEUED. In-flight PROBING tasks (≤ worker concurrency) finish
    naturally. Returns how many pending pairs were stopped.
    """
    from sqlalchemy import update
    result = db.execute(
        update(CoverageSnapshot)
        .where(
            CoverageSnapshot.project_id == project_id,
            CoverageSnapshot.status == CellState.QUEUED,
        )
        .values(status=CellState.UNPROBED)
    )
    db.commit()
    return result.rowcount or 0


def count_queued(db: Session, project_id: UUID | None = None) -> int:
    """Total QUEUED count for a project — the TRUE number of pairs to collect,
    independent of the list_queued page limit (so the UI can show the real total)."""
    from sqlalchemy import func, select
    q = select(func.count()).select_from(CoverageSnapshot).where(
        CoverageSnapshot.status == CellState.QUEUED
    )
    if project_id is not None:
        q = q.where(CoverageSnapshot.project_id == project_id)
    return db.scalar(q) or 0


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


def reclaim_stuck_probing(
    db: Session,
    project_id: UUID | None = None,
    *,
    older_than: timedelta = STUCK_PROBING_AFTER,
) -> int:
    """Release pairs abandoned in PROBING back to a terminal state. Returns count.

    A crashed worker (or a killed request) leaves its pair in PROBING forever:
    PROBING is only reachable from QUEUED, so the pair can never be re-queued and
    silently drops out of collection. Anything stuck past `older_than` is moved to
    REJECTED_EMPTY — a legal PROBING transition, and one that MANUAL_PIN can
    re-queue from — so the pair becomes collectable again.
    """
    cutoff = datetime.now(timezone.utc) - older_than
    q = db.query(CoverageSnapshot).filter(
        CoverageSnapshot.status == CellState.PROBING,
        CoverageSnapshot.last_probed_at < cutoff,
    )
    if project_id is not None:
        q = q.filter(CoverageSnapshot.project_id == project_id)

    stuck = q.all()
    for snapshot in stuck:
        transition_state(
            db,
            snapshot.cell_id,
            snapshot.competitor_id,
            CellState.REJECTED_EMPTY,
            note="reclaim: probe abandoned in PROBING",
        )
    return len(stuck)
