"""Celery task: run a generic async Job by delegating to job_service.execute_job."""
from uuid import UUID

from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.workers.celery_app import celery_app
from app.services.job_service import execute_job

logger = get_task_logger(__name__)


@celery_app.task(name="app.workers.tasks.run_job.run", bind=True)
def run_job(self, job_id: str):
    """Execute a queued Job (discover / grid_gen / insight_gen / report_compose).

    execute_job always lands the job on a terminal state (done/failed), so a
    job never gets stuck in running even if the underlying AI call throws.
    """
    logger.info(f"run_job start: {job_id}")
    db = SessionLocal()
    try:
        execute_job(db, UUID(job_id))
    finally:
        db.close()
    logger.info(f"run_job done: {job_id}")
    return {"job_id": job_id}
