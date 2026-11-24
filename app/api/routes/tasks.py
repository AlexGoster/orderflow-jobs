from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_session
from app.models import TaskState, User
from app.schemas import TaskStateRead
from app.services import tasks as tasks_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskStateRead])
async def list_tasks(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TaskState]:
    return await tasks_service.list_task_states(
        session, user_id=user.id, offset=offset, limit=limit
    )


@router.get("/{task_ref}", response_model=TaskStateRead)
async def get_task(
    task_ref: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskState:
    """Статус фоновой задачи: task_ref = id из 202-ответа либо числовой id записи."""
    return await tasks_service.get_task_state(session, task_ref, user.id)
