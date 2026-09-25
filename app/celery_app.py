from datetime import timedelta
from typing import Any

from celery import Celery
from celery.schedules import crontab
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "orderflow_jobs",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.emails",
        "app.tasks.invoices",
        "app.tasks.stats",
        "app.tasks.cleanup",
    ],
)

#: Единая политика надёжности для всех задач проекта.
TASK_RETRY_OPTIONS: dict[str, Any] = {
    "autoretry_for": (OperationalError, ConnectionError, TimeoutError),
    "retry_backoff": True,
    "retry_backoff_max": 600,
    "retry_jitter": True,
    "max_retries": 5,
}

celery_app.conf.update(
    task_always_eager=settings.celery_always_eager,
    task_eager_propagates=settings.celery_task_eager_propagates,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=timedelta(days=1),
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "cleanup-expired-orders": {
            "task": "tasks.cleanup_expired_orders",
            "schedule": crontab(minute=0),
            "options": {"expires": 3600},
        },
        "daily-orders-stats": {
            "task": "tasks.recompute_daily_stats",
            "schedule": crontab(hour=0, minute=5),
            "options": {"expires": 6 * 3600},
        },
    },
)
