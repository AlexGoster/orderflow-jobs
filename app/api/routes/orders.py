from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_session
from app.models import Order, User
from app.schemas import OrderCreate, OrderRead, TaskAccepted
from app.services import orders as orders_service
from app.services import tasks as tasks_service
from app.tasks import generate_invoice_pdf, send_order_email

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Order:
    order = await orders_service.create_order(session, user.id, payload)
    if get_settings().order_email_enabled:
        send_order_email.delay(order.id)
    return order


@router.get("", response_model=list[OrderRead])
async def list_orders(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Order]:
    return await orders_service.list_orders(session, user.id)


@router.get("/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Order:
    return await orders_service.get_order(session, user.id, order_id)


@router.post(
    "/{order_id}/invoice",
    response_model=TaskAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_invoice(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskAccepted:
    """Ставит генерацию счёта в очередь и сразу возвращает task_id для polling."""
    order = await orders_service.get_order(session, user.id, order_id)
    state = await tasks_service.create_task_state(
        session, name=generate_invoice_pdf.name or "tasks.generate_invoice_pdf"
    )
    generate_invoice_pdf.apply_async(kwargs={"order_id": order.id}, task_id=state.celery_task_id)
    await session.refresh(state)

    task_id = state.celery_task_id or ""
    return TaskAccepted(
        task_id=task_id,
        status=state.status,
        status_url=f"/api/v1/tasks/{task_id}",
    )
