import logging
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from celery import Task
from sqlalchemy import select

from app.celery_app import TASK_RETRY_OPTIONS, celery_app
from app.core.database import get_sync_session_factory
from app.models import DailyStat, Order
from app.tasks.tracking import track_task

logger = logging.getLogger(__name__)


def default_day() -> date:
    """Отчёт строится за вчерашний день (UTC) — так суточный срез закрыт полностью."""
    return (datetime.now(UTC) - timedelta(days=1)).date()


@celery_app.task(bind=True, name="tasks.recompute_daily_stats", **TASK_RETRY_OPTIONS)
@track_task
def recompute_daily_stats(self: Task, day: str | None = None) -> dict[str, Any]:
    """Агрегация заказов за день с upsert в daily_stats — запускать хоть 10 раз подряд."""
    target = default_day() if day is None else date.fromisoformat(day)
    start = datetime.combine(target, time.min, tzinfo=UTC)
    end = start + timedelta(days=1)

    with get_sync_session_factory()() as session:
        orders = list(
            session.scalars(select(Order).where(Order.created_at >= start, Order.created_at < end))
        )
        orders_count = len(orders)
        items_count = sum(len(order.items) for order in orders)
        total = sum((Decimal(str(order.total)) for order in orders), Decimal("0"))

        stat = session.scalar(select(DailyStat).where(DailyStat.day == target))
        if stat is None:
            stat = DailyStat(day=target)
            session.add(stat)
        stat.orders_count = orders_count
        stat.items_count = items_count
        stat.total_revenue = total
        session.commit()

    logger.info("daily stats day=%s orders=%s revenue=%s", target, orders_count, total)
    return {
        "day": target.isoformat(),
        "orders": orders_count,
        "items": items_count,
        "revenue": str(total),
    }
