import json
from typing import Any, Protocol, cast

import redis.asyncio as aioredis

from app.core.config import get_settings


class RedisClient(Protocol):
    """Минимальный интерфейс доступа к Redis: в тестах подменяется fakeredis."""

    async def get(self, name: str) -> bytes | str | None: ...

    async def set(self, name: str, value: bytes, ex: int | None = None) -> Any: ...

    async def delete(self, *names: str) -> Any: ...

    async def publish(self, channel: str, message: str) -> int: ...

    async def ping(self) -> bool: ...


_client: RedisClient | None = None


def get_redis() -> RedisClient:
    global _client
    if _client is None:
        _client = cast(RedisClient, aioredis.from_url(get_settings().redis_url))
    return _client


def set_redis(client: RedisClient | None) -> None:
    global _client
    _client = client


def reset_redis() -> None:
    set_redis(None)


def _decode(raw: bytes | str | None) -> str | None:
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else raw


async def cache_get(key: str) -> str | None:
    return _decode(await get_redis().get(key))


async def cache_set(key: str, value: str, ttl: int | None = None) -> None:
    await get_redis().set(key, value.encode(), ex=ttl)


async def cache_delete(*keys: str) -> None:
    if keys:
        await get_redis().delete(*keys)


async def publish_event(channel: str, payload: dict[str, Any]) -> int:
    message = json.dumps(payload, ensure_ascii=False, default=str)
    return await get_redis().publish(channel, message)
