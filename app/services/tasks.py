from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import TaskOwnership, TaskState, TaskStatus


async def create_task_state(session: AsyncSession, name: str, user_id: int) -> TaskState:
    """Создаёт запись статуса до постановки задачи в очередь (id задачи = её celery id)."""
    state = TaskState(
        name=name,
        status=TaskStatus.pending,
        celery_task_id=str(uuid4()),
        attempts=0,
    )
    session.add(state)
    await session.flush()
    session.add(TaskOwnership(task_id=state.id, user_id=user_id))
    await session.commit()
    await session.refresh(state)
    return state


async def get_task_state(session: AsyncSession, task_ref: str, user_id: int) -> TaskState:
    reference = (
        TaskState.id == int(task_ref)
        if task_ref.isdigit()
        else TaskState.celery_task_id == task_ref
    )
    state = await session.scalar(
        select(TaskState).join(TaskOwnership).where(TaskOwnership.user_id == user_id, reference)
    )
    if state is None:
        raise NotFoundError("Task not found")
    return state


async def list_task_states(
    session: AsyncSession, *, user_id: int, offset: int = 0, limit: int = 50
) -> list[TaskState]:
    result = await session.scalars(
        select(TaskState)
        .join(TaskOwnership)
        .where(TaskOwnership.user_id == user_id)
        .order_by(TaskState.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result)
