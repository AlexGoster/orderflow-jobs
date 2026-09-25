from collections.abc import AsyncIterator, Iterator

import pytest
from fakeredis import aioredis as fake_aioredis
from httpx import ASGITransport, AsyncClient

from app.celery_app import celery_app
from app.core.config import Settings, get_settings, reset_settings_cache
from app.core.database import dispose_engine, dispose_sync_engine, get_engine
from app.core.redis import reset_redis, set_redis
from app.main import app
from app.models import Base


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch) -> Iterator[Settings]:
    """Окружение каждого теста: свежая SQLite-БД, fakeredis, Celery в eager mode."""
    db_file = tmp_path / "orderflow.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}")
    monkeypatch.setenv("INVOICE_DIR", (tmp_path / "invoices").as_posix())
    monkeypatch.setenv("CELERY_ALWAYS_EAGER", "true")
    monkeypatch.setenv("CELERY_TASK_EAGER_PROPAGATES", "false")
    reset_settings_cache()

    set_redis(fake_aioredis.FakeRedis())
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    celery_app.conf.broker_url = "memory://"
    celery_app.conf.result_backend = "cache+memory://"

    yield get_settings()

    dispose_sync_engine()
    reset_redis()
    reset_settings_cache()


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await dispose_engine()


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict[str, str]:
    email = "user@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "secret-pass-1", "full_name": "Test User"},
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "secret-pass-1"}
    )
    data = resp.json()
    return {"email": email, "token": data["access_token"]}


@pytest.fixture
async def auth_headers(registered_user: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {registered_user['token']}"}


@pytest.fixture
def product_payload() -> dict[str, object]:
    return {"sku": "SKU-1", "name": "Desk Lamp", "price": 1500.0, "stock": 5}
