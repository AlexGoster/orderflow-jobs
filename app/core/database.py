from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def to_sync_url(url: str) -> str:
    """Async URL -> прямой драйвер (нужен Celery-воркеру: он работает без event loop)."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://").replace(
        "sqlite+aiosqlite://", "sqlite://"
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


def get_sync_engine() -> Engine:
    global _sync_engine
    if _sync_engine is None:
        url = to_sync_url(get_settings().database_url)
        connect_args: dict[str, Any] = {"timeout": 30} if url.startswith("sqlite") else {}
        _sync_engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    return _sync_engine


def get_sync_session_factory() -> sessionmaker[Session]:
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(get_sync_engine(), expire_on_commit=False)
    return _sync_session_factory


def dispose_sync_engine() -> None:
    """Освобождает пул синхронического движка (используется в teardown тестов)."""
    global _sync_engine, _sync_session_factory
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None
        _sync_session_factory = None


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
    dispose_sync_engine()
