import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.redis import cache_delete, cache_get, cache_set
from app.models import Product
from app.schemas import ProductCreate, ProductUpdate

PRODUCT_CACHE_PREFIX = "products:item"


def item_cache_key(product_id: int) -> str:
    return f"{PRODUCT_CACHE_PREFIX}:{product_id}"


def _to_cache(product: Product) -> str:
    return json.dumps(
        {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "price": str(product.price),
            "stock": product.stock,
            "created_at": product.created_at.isoformat(),
        },
        ensure_ascii=False,
    )


def _from_cache(payload: str) -> Product:
    data = json.loads(payload)
    return Product(
        id=data["id"],
        sku=data["sku"],
        name=data["name"],
        price=Decimal(data["price"]),
        stock=data["stock"],
        created_at=datetime.fromisoformat(data["created_at"]),
    )


async def list_products(
    session: AsyncSession, *, offset: int = 0, limit: int = 50
) -> list[Product]:
    result = await session.scalars(select(Product).order_by(Product.id).offset(offset).limit(limit))
    return list(result)


async def get_product(session: AsyncSession, product_id: int) -> Product:
    """Чтение товара с кэшем в Redis; промах по кэшу идёт в БД."""
    key = item_cache_key(product_id)
    cached = await cache_get(key)
    if cached is not None:
        return _from_cache(cached)

    product = await session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")

    await cache_set(key, _to_cache(product), ttl=get_settings().cache_ttl_seconds)
    return product


async def create_product(session: AsyncSession, payload: ProductCreate) -> Product:
    existing = await session.scalar(select(Product).where(Product.sku == payload.sku))
    if existing is not None:
        raise ConflictError(f"SKU {payload.sku} already exists")
    product = Product(**payload.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def update_product(session: AsyncSession, product_id: int, payload: ProductUpdate) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")

    if payload.name is not None:
        product.name = payload.name
    if payload.price is not None:
        product.price = Decimal(str(payload.price))
    if payload.stock is not None:
        product.stock = payload.stock

    await session.commit()
    await session.refresh(product)
    await cache_delete(item_cache_key(product_id))
    return product


async def delete_product(session: AsyncSession, product_id: int) -> None:
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found")
    await session.delete(product)
    await session.commit()
    await cache_delete(item_cache_key(product_id))
