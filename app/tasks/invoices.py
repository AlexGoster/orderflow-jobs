import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from celery import Task
from sqlalchemy import select

from app.celery_app import TASK_RETRY_OPTIONS, celery_app
from app.core.config import get_settings
from app.core.database import get_sync_session_factory
from app.core.exceptions import NotFoundError
from app.models import Order, Product, User
from app.tasks.tracking import track_task

logger = logging.getLogger(__name__)

SEPARATOR = "-" * 48


def render_invoice(order: Order, recipient: str, products: dict[int, str]) -> str:
    lines = [
        "ORDERFLOW / INVOICE",
        f"Order:    #{order.id}",
        f"Customer: {recipient}",
        f"Created:  {order.created_at.isoformat()}",
        f"Status:   {order.status.value}",
        SEPARATOR,
    ]
    for item in order.items:
        title = products.get(item.product_id, f"product#{item.product_id}")
        line_total = Decimal(str(item.unit_price)) * item.quantity
        lines.append(f"{item.quantity:>4} x {title[:28]:<28} {line_total:>12}")
    lines += [SEPARATOR, f"{'TOTAL':<40}{order.total:>8}", ""]
    return "\n".join(lines)


@celery_app.task(bind=True, name="tasks.generate_invoice_pdf", **TASK_RETRY_OPTIONS)
@track_task
def generate_invoice_pdf(self: Task, order_id: int) -> dict[str, Any]:
    """Текстовый «чек» по заказу в файл. Повторный запуск перезаписывает тот же файл."""
    settings = get_settings()
    with get_sync_session_factory()() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")

        user = session.get(User, order.user_id)
        recipient = user.email if user is not None else "unknown@example.com"
        product_ids = [item.product_id for item in order.items]
        products = {
            product.id: product.name
            for product in session.scalars(select(Product).where(Product.id.in_(product_ids)))
        }
        content = render_invoice(order, recipient, products)

        path = Path(settings.invoice_dir) / f"order_{order.id}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        order.invoice_path = str(path)
        session.commit()

    logger.info("invoice generated order=%s path=%s", order_id, path)
    return {"order_id": order_id, "path": str(path), "size": len(content)}
