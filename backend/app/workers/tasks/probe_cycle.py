from uuid import UUID

from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.workers.celery_app import celery_app
from app.services.m3_collection.probe_runner import run_probe

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.probe_cycle.run",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
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
        from app.services.m3_collection.coverage_state_service import get_or_create_snapshot
        snap = get_or_create_snapshot(db, UUID(cell_id), UUID(competitor_id))
        if snap.status != "QUEUED":
            logger.info(f"Probe cycle skipped (not QUEUED, status={snap.status}): {cell_id}/{competitor_id}")
            return {"status": "skipped", "state": snap.status}
        result = run_probe(db, UUID(cell_id), UUID(competitor_id))
    finally:
        db.close()
    logger.info(
        f"Probe cycle done: cell={cell_id} competitor={competitor_id} "
        f"found={result.get('candidates_found')} passed={result.get('passed')} "
        f"state={result.get('state')}"
    )
    return {"status": "done", **result}
