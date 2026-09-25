import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from celery import Task
from sqlalchemy import update

from app.celery_app import TASK_RETRY_OPTIONS, celery_app
from app.core.config import get_settings
from app.core.database import get_sync_session_factory
from app.models import Order, OrderStatus
from app.tasks.tracking import track_task

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.cleanup_expired_orders", **TASK_RETRY_OPTIONS)
@track_task
def cleanup_expired_orders(self: Task, older_than_days: int | None = None) -> dict[str, Any]:
    """Отменяет слишком старые pending-заказы. Идемпотентно: второй запуск меняет 0 строк."""
    days = get_settings().stale_order_days if older_than_days is None else older_than_days
    cutoff = datetime.now(UTC) - timedelta(days=days)

    with get_sync_session_factory()() as session:
        result = session.execute(
            update(Order)
            .where(Order.status == OrderStatus.pending, Order.created_at < cutoff)
            .values(status=OrderStatus.cancelled)
            .execution_options(synchronize_session=False)
        )
        session.commit()

    cancelled = int(getattr(result, "rowcount", 0) or 0)
    logger.info("cleanup: cancelled=%s older_than_days=%s", cancelled, days)
    return {"cancelled": cancelled, "older_than_days": days, "cutoff": cutoff.isoformat()}
