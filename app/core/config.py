from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OrderFlow Jobs"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://orderflow:orderflow@localhost:5432/orderflow"

    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"

    cors_origins: list[str] = ["http://localhost:3000"]

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_always_eager: bool = False
    celery_task_eager_propagates: bool = False

    redis_url: str = "redis://localhost:6379/2"
    cache_ttl_seconds: int = 60

    invoice_dir: str = "data/invoices"
    stale_order_days: int = 30
    order_email_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Сбрасывает кэш настроек — нужно, когда тест меняет переменные окружения."""
    get_settings.cache_clear()
