from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "ux_benchmarks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.workers.adapters.*": {"queue": "adapters"},
        "app.workers.scoring.*": {"queue": "scoring"},
    },
)
