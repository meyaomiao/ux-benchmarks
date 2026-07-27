from celery import Celery
from celery.utils.log import get_task_logger
from app.core.config import settings

logger = get_task_logger(__name__)

celery_app = Celery(
    "ux_benchmarks",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.health",
        "app.workers.tasks.probe_cycle",
        "app.workers.tasks.run_job",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        # A whole probe owns its browser work synchronously. Routing the parent
        # task avoids nested Celery result waits while the dedicated worker's
        # concurrency is the hard Chromium cap.
        "app.workers.tasks.probe_cycle.*": {"queue": "browser"},
        "app.workers.tasks.run_job.*": {"queue": "adapters"},
        "app.workers.tasks.scoring.*": {"queue": "scoring"},
        # Health tasks stay on the general worker.
        "app.workers.tasks.health.*": {"queue": "adapters"},
    },
    beat_schedule={
        "freshness-decay-check": {
            "task": "app.workers.tasks.health.ping",
            "schedule": 3600.0,  # 每小时，Phase 2 换成真正的 freshness check
        },
    },
)
