from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.workers.celery_app import celery_app
from app.services.m3_collection.coverage_state_service import transition_state
from app.services.m3_collection.state_machine import CellState

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.probe_cycle.run",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_probe_cycle(self, cell_id: str, competitor_id: str):
    """
    Run a probe cycle for a single (cell, competitor) pair.

    Phase 0 note: adapters + AI scoring are issues #17-20 and remain stubbed.
    This task does NOT call any adapters. It only drives the state machine:
    the queued pair is transitioned QUEUED -> PROBING and a structured result
    is returned.

    Steps (to be implemented in later issues):
    1. Query expansion (issue #15)
    2. Adapter fan-out (issues #17, #18)
    3. AI relevance scoring (issue #19)
    4. Dedup + shortlist (issue #20)
    5. Finalise cell state machine (SHORTLIST_READY / REJECTED_EMPTY)
    """
    logger.info(f"Probe cycle start: cell={cell_id} competitor={competitor_id}")

    db = SessionLocal()
    try:
        snapshot = transition_state(
            db,
            cell_id,
            competitor_id,
            CellState.PROBING,
            note="probe_cycle.run",
        )
        status = snapshot.status
        probe_cycles = snapshot.probe_cycles
    finally:
        db.close()

    logger.info(
        f"Probe cycle transitioned to PROBING: cell={cell_id} "
        f"competitor={competitor_id} probe_cycles={probe_cycles}"
    )
    return {
        "status": "probing",
        "cell_id": cell_id,
        "competitor_id": competitor_id,
        "state": status,
        "probe_cycles": probe_cycles,
        "message": "Adapters + scoring stubbed (issues #17-20)",
    }
