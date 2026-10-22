import functools
import inspect
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from celery import Task
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_sync_session_factory
from app.models import Order, TaskOwnership, TaskState, TaskStatus

P = ParamSpec("P")
R = TypeVar("R")


def _find_state(session: Session, task_id: str) -> TaskState | None:
    return session.scalar(select(TaskState).where(TaskState.celery_task_id == task_id))


def _begin(name: str, task_id: str | None, order_id: int | None) -> int:
    """Создаёт или переиспользует запись статуса (её же обновляет каждая попытка)."""
    with get_sync_session_factory()() as session:
        state = _find_state(session, task_id) if task_id is not None else None
        if state is None:
            state = TaskState(
                name=name,
                status=TaskStatus.running,
                celery_task_id=task_id,
                attempts=1,
            )
            session.add(state)
        else:
            state.status = TaskStatus.running
            state.attempts += 1
            state.error = None
            state.finished_at = None
        session.flush()
        if order_id is not None and session.get(TaskOwnership, state.id) is None:
            order = session.get(Order, order_id)
            if order is not None:
                session.add(TaskOwnership(task_id=state.id, user_id=order.user_id))
        session.commit()
        session.refresh(state)
        return state.id


def _finish(
    state_id: int,
    *,
    status: TaskStatus,
    error: BaseException | None = None,
    result: Any = None,
) -> None:
    with get_sync_session_factory()() as session:
        state = session.get(TaskState, state_id)
        if state is None:
            return
        state.status = status
        state.finished_at = datetime.now(UTC)
        state.error = f"{type(error).__name__}: {error}" if error is not None else None
        state.result = (
            None if result is None else json.dumps(result, ensure_ascii=False, default=str)
        )
        session.commit()


def track_task(func: Callable[P, R]) -> Callable[P, R]:
    """Декоратор задачи: running -> success|failed в таблице task_states.

    Ставится под `@celery_app.task(bind=True, ...)`: тогда первым аргументом
    приходит экземпляр задачи с `request.id` (celery id совпадает с celery_task_id).
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> R:
        task = args[0] if args and isinstance(args[0], Task) else None
        task_id = task.request.id if task is not None else None
        name = (task.name if task is not None else None) or func.__name__

        # Bind by the actual signature: Celery supports both positional and keyword arguments.
        order_id = inspect.signature(func).bind(*args, **kwargs).arguments.get("order_id")
        state_id = _begin(name, task_id, order_id)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            _finish(state_id, status=TaskStatus.failed, error=exc)
            raise
        _finish(state_id, status=TaskStatus.success, result=result)
        return result

    return wrapper
