from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import get_engine
from app.core.redis import cache_get, get_redis

PRODUCT: dict[str, Any] = {"sku": "SKU-1", "name": "Desk Lamp", "price": 1500.0, "stock": 5}


async def _create(client: AsyncClient) -> int:
    resp = await client.post("/api/v1/products", json=PRODUCT)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_product_crud(client: AsyncClient) -> None:
    product_id = await _create(client)

    listed = await client.get("/api/v1/products")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = await client.get(f"/api/v1/products/{product_id}")
    assert fetched.status_code == 200
    assert fetched.json()["sku"] == "SKU-1"


async def test_duplicate_sku_rejected(client: AsyncClient) -> None:
    await _create(client)
    dup = await client.post("/api/v1/products", json=PRODUCT)
    assert dup.status_code == 409


async def test_product_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/products/999")
    assert resp.status_code == 404


async def test_update_product(client: AsyncClient) -> None:
    product_id = await _create(client)
    resp = await client.patch(f"/api/v1/products/{product_id}", json={"price": 1299.0, "stock": 7})
    assert resp.status_code == 200
    assert resp.json()["price"] == 1299.0
    assert resp.json()["stock"] == 7

    assert (
        await client.patch(f"/api/v1/products/{product_id}", json={"price": -1})
    ).status_code == 422


async def test_delete_product(client: AsyncClient) -> None:
    product_id = await _create(client)
    resp = await client.delete(f"/api/v1/products/{product_id}")
    assert resp.status_code == 204
    assert (await client.get(f"/api/v1/products/{product_id}")).status_code == 404


async def test_product_read_is_served_from_redis_cache(client: AsyncClient) -> None:
    product_id = await _create(client)
    first = await client.get(f"/api/v1/products/{product_id}")
    assert first.json()["name"] == "Desk Lamp"
    assert await cache_get(f"products:item:{product_id}") is not None

    # меняем строку в БД мимо сервиса — инвалидации не было, ответ должен устареть
    async with get_engine().connect() as conn:
        await conn.execute(
            text("UPDATE products SET name = 'HACKED' WHERE id = :id"), {"id": product_id}
        )
        await conn.commit()

    cached = await client.get(f"/api/v1/products/{product_id}")
    assert cached.json()["name"] == "Desk Lamp"


async def test_update_invalidates_product_cache(client: AsyncClient) -> None:
    product_id = await _create(client)
    await client.get(f"/api/v1/products/{product_id}")
    assert await cache_get(f"products:item:{product_id}") is not None

    patched = await client.patch(f"/api/v1/products/{product_id}", json={"price": 999.0})
    assert patched.json()["price"] == 999.0
    assert await cache_get(f"products:item:{product_id}") is None

    fresh = await client.get(f"/api/v1/products/{product_id}")
    assert fresh.json()["price"] == 999.0


async def test_delete_invalidates_product_cache(client: AsyncClient) -> None:
    product_id = await _create(client)
    await client.get(f"/api/v1/products/{product_id}")
    assert await cache_get(f"products:item:{product_id}") is not None

    await client.delete(f"/api/v1/products/{product_id}")
    assert await cache_get(f"products:item:{product_id}") is None
    assert await get_redis().get(f"products:item:{product_id}") is None
