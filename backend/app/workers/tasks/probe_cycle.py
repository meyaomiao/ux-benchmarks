from celery.utils.log import get_task_logger
from app.workers.celery_app import celery_app

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
    Phase 0 stub — full implementation in issue #14.

    Steps (to be implemented):
    1. Query expansion (issue #15)
    2. Adapter fan-out (issues #17, #18)
    3. AI relevance scoring (issue #19)
    4. Dedup + shortlist (issue #20)
    5. Update cell state machine
    """
    logger.info(f"Probe cycle stub: cell={cell_id} competitor={competitor_id}")
    return {
        "status": "stub",
        "cell_id": cell_id,
        "competitor_id": competitor_id,
        "message": "Full implementation in issue #14",
    }
