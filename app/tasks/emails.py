import logging
from typing import Any

from celery import Task

from app.celery_app import TASK_RETRY_OPTIONS, celery_app
from app.core.database import get_sync_session_factory
from app.core.exceptions import NotFoundError
from app.models import Order, User
from app.tasks.tracking import track_task

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.send_order_email", **TASK_RETRY_OPTIONS)
@track_task
def send_order_email(self: Task, order_id: int) -> dict[str, Any]:
    """Имитация письма о заказе: без SMTP — только лог и статус в БД (идемпотентно)."""
    with get_sync_session_factory()() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        user = session.get(User, order.user_id)
        recipient = user.email if user is not None else "unknown@example.com"
        total = str(order.total)
        items_count = len(order.items)

    payload: dict[str, Any] = {
        "order_id": order_id,
        "to": recipient,
        "subject": f"Order #{order_id} confirmed",
        "items": items_count,
        "total": total,
        "simulated": True,
    }
    logger.info(
        "simulated email to=%s subject=%r order=%s total=%s",
        recipient,
        payload["subject"],
        order_id,
        total,
    )
    return payload
