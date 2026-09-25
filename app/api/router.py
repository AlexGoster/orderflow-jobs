from fastapi import APIRouter

from app.api.routes import auth, orders, products, tasks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(orders.router)
api_router.include_router(tasks.router)
