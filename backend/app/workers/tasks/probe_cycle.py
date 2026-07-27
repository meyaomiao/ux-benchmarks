from uuid import UUID

from billiard.exceptions import SoftTimeLimitExceeded
from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.services.m3_collection.probe_runner import run_probe
from app.services.m3_collection.coverage_state_service import (
    get_or_create_snapshot,
    transition_state,
)
from app.services.m3_collection.state_machine import CellState
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)

PROBE_SOFT_TIME_LIMIT = 12 * 60
PROBE_HARD_TIME_LIMIT = 14 * 60


def _is_redelivered(task) -> bool:
    """Return whether the broker redelivered a task after worker loss."""
    delivery_info = getattr(task.request, "delivery_info", None) or {}
    return bool(delivery_info.get("redelivered"))


def _finish_probing(db, cell_id: UUID, competitor_id: UUID, *, note: str):
    """Move an abandoned probe out of PROBING without masking DB errors."""
    db.rollback()
    snapshot = get_or_create_snapshot(db, cell_id, competitor_id)
    if snapshot.status == CellState.PROBING:
        snapshot = transition_state(
            db,
            str(cell_id),
            str(competitor_id),
            CellState.REJECTED_EMPTY,
            note=note,
        )
    return snapshot


@celery_app.task(
    name="app.workers.tasks.probe_cycle.run",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=PROBE_SOFT_TIME_LIMIT,
    time_limit=PROBE_HARD_TIME_LIMIT,
)
def run_probe_cycle(self, cell_id: str, competitor_id: str):
    """Run one probe cycle for a (cell, competitor) pair via run_probe.

    Delegates to the single, robust implementation in probe_runner.run_probe:
    it normalises any prior state → QUEUED → PROBING (avoiding the
    REJECTED_EMPTY→PROBING crash), runs search+fetch+scoring, and ALWAYS lands
    on a terminal state (SHORTLIST_READY / REJECTED_EMPTY) even on error — so a
    pair can never get stuck in PROBING. One source of truth for probe logic.
    """
    logger.info(f"Probe cycle start: cell={cell_id} competitor={competitor_id}")
    db = SessionLocal()
    try:
        # Cooperative cancel: a task is only run if its pair is still QUEUED.
        # "Stop collection" resets pending QUEUED rows → UNPROBED, so tasks still
        # waiting in the broker see a non-QUEUED status here and skip cheaply
        # (before the expensive search+fetch+score). Already-PROBING tasks (≤ the
        # worker concurrency) finish naturally.
        snap = get_or_create_snapshot(db, UUID(cell_id), UUID(competitor_id))
        if snap.status != "QUEUED":
            # A hard time limit kills the child process after the soft-limit
            # cleanup window. With late acknowledgements and
            # task_reject_on_worker_lost, the message is redelivered here; only
            # that explicit redelivery is allowed to reclaim an old PROBING row.
            if snap.status == CellState.PROBING and _is_redelivered(self):
                recovered = _finish_probing(
                    db,
                    UUID(cell_id),
                    UUID(competitor_id),
                    note="probe-cycle: recovered after worker hard timeout",
                )
                logger.warning(
                    "Probe cycle recovered redelivered PROBING pair: %s/%s",
                    cell_id,
                    competitor_id,
                )
                return {"status": "recovered", "state": recovered.status}
            logger.info(f"Probe cycle skipped (not QUEUED, status={snap.status}): {cell_id}/{competitor_id}")
            return {"status": "skipped", "state": snap.status}
        try:
            result = run_probe(db, UUID(cell_id), UUID(competitor_id))
        except SoftTimeLimitExceeded:
            snapshot = _finish_probing(
                db,
                UUID(cell_id),
                UUID(competitor_id),
                note="probe-cycle: soft time limit exceeded",
            )
            logger.warning(
                "Probe cycle soft timeout: %s/%s state=%s",
                cell_id,
                competitor_id,
                snapshot.status,
            )
            return {
                "status": "timeout",
                "state": snapshot.status,
                "error": "soft time limit exceeded",
            }
        except Exception:
            # Keep an unexpected browser/LLM/persistence failure from leaving a
            # pair in PROBING, then preserve the original task failure signal.
            _finish_probing(
                db,
                UUID(cell_id),
                UUID(competitor_id),
                note="probe-cycle: task failure",
            )
            raise
    finally:
        db.close()
    logger.info(
        f"Probe cycle done: cell={cell_id} competitor={competitor_id} "
        f"found={result.get('candidates_found')} passed={result.get('passed')} "
        f"state={result.get('state')}"
    )
    return {"status": "done", **result}
