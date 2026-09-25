from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import TaskState, TaskStatus


async def create_task_state(session: AsyncSession, name: str) -> TaskState:
    """Создаёт запись статуса до постановки задачи в очередь (id задачи = её celery id)."""
    state = TaskState(
        name=name,
        status=TaskStatus.pending,
        celery_task_id=str(uuid4()),
        attempts=0,
    )
    session.add(state)
    await session.commit()
    await session.refresh(state)
    return state


async def get_task_state(session: AsyncSession, task_ref: str) -> TaskState:
    if task_ref.isdigit():
        state = await session.get(TaskState, int(task_ref))
    else:
        state = await session.scalar(select(TaskState).where(TaskState.celery_task_id == task_ref))
    if state is None:
        raise NotFoundError("Task not found")
    return state


async def list_task_states(
    session: AsyncSession, *, offset: int = 0, limit: int = 50
) -> list[TaskState]:
    result = await session.scalars(
        select(TaskState).order_by(TaskState.id.desc()).offset(offset).limit(limit)
    )
    return list(result)
