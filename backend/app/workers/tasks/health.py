from celery.utils.log import get_task_logger
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)

@celery_app.task(name="app.workers.tasks.health.ping", bind=True)
def ping(self):
    """Health check task — 验证 worker 存活."""
    logger.info("Worker ping: OK")
    return {"status": "ok", "worker": self.request.hostname}
