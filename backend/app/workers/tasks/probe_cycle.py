from uuid import UUID

from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.workers.celery_app import celery_app
from app.services.m3_collection.coverage_state_service import transition_state
from app.services.m3_collection.state_machine import CellState
from app.services.m3_collection.pipeline import run_probe_pipeline

logger = get_task_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.probe_cycle.run",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_probe_cycle(self, cell_id: str, competitor_id: str):
    """
    Run one probe cycle for a single (cell, competitor) pair, end to end:

    1. QUEUED -> PROBING
    2. query expansion -> adapter fetch -> AI relevance scoring (pipeline)
    3. PROBING -> SHORTLIST_READY (passers found) or REJECTED_EMPTY (none)

    Persistence of accepted assets and dedup/ranking are separate issues
    (#20 dedup, #22 asset store); this task drives the state machine and
    returns the in-memory scored result. Live network/AI only fire when
    settings.use_collection_mock is False — otherwise the pipeline runs on
    deterministic fixtures, so this task is safe to run offline.
    """
    logger.info(f"Probe cycle start: cell={cell_id} competitor={competitor_id}")

    db = SessionLocal()
    try:
        # 1. Enter PROBING.
        transition_state(
            db, cell_id, competitor_id, CellState.PROBING, note="probe_cycle.run"
        )

        # 2. Fetch -> score.
        result = run_probe_pipeline(db, UUID(cell_id), UUID(competitor_id))

        # 3. Finalise: passers -> SHORTLIST_READY, else REJECTED_EMPTY.
        final = (
            CellState.SHORTLIST_READY if result.has_passers else CellState.REJECTED_EMPTY
        )
        snapshot = transition_state(
            db, cell_id, competitor_id, final, note="probe_cycle.finalise"
        )
        status = snapshot.status
        probe_cycles = snapshot.probe_cycles
    finally:
        db.close()

    logger.info(
        f"Probe cycle done: cell={cell_id} competitor={competitor_id} "
        f"found={result.candidates_found} passed={len(result.passed)} state={status}"
    )
    return {
        "status": "done",
        "cell_id": cell_id,
        "competitor_id": competitor_id,
        "state": status,
        "probe_cycles": probe_cycles,
        "candidates_found": result.candidates_found,
        "passed": len(result.passed),
    }
