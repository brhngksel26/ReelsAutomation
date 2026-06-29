from __future__ import annotations

import logging
import os
from random import randint

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.enums import LLMProviderType


class GlobalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "development"

    # Logging
    LOG_LEVEL: int = logging.DEBUG

    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: str
    DB_NAME: str
    DB_SCHEMA: str
    # specify single database url
    DB_URL: str | None = None
    POSTGRES_CONTAINER_PORT: str

    # Redis
    REDIS_HOST: str
    REDIS_PORT: str
    REDIS_PASSWORD: str
    REDIS_CACHE_EXPIRATION_SECONDS: int
    REDIS_DB: int
    REDIS_CONTAINER_PORT: int

    CACHE_DURATION: int = 2592000  # 30 days in seconds
    REQUEST_TIMEOUT: int = 30

    # HTTP client (httpx)
    HTTP_CONNECT_TIMEOUT: float = 3.0
    HTTP_READ_TIMEOUT: float = 15.0
    HTTP_WRITE_TIMEOUT: float = 5.0
    HTTP_POOL_TIMEOUT: float = 2.0
    HTTP_MAX_CONNECTIONS: int = 50
    HTTP_MAX_KEEPALIVE: int = 20
    HTTP_HTTP2_ENABLED: bool = True

    JWT_ACCESS_SECRET_KEY: str
    JWT_REFRESH_SECRET_KEY: str
    ENCRYPTION_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: str
    NEW_ACCESS_TOKEN_EXPIRE_MINUTES: str
    REFRESH_TOKEN_EXPIRE_MINUTES: str
    SESSION_SECRET_KEY: str
    SESSION_EXPIRE_HOURS: int

    RATE_LIMIT_API_PREFIX: str = "/api/v1/"
    RATE_LIMIT_EXCLUDED: str = "/docs,/openapi.json,/redoc"

    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    ENABLE_RATE_LIMITING: bool = True
    REDIS_ENABLED: bool = True

    # LLM
    LLM_PROVIDER: LLMProviderType = LLMProviderType.OLLAMA
    LLM_MODEL_NAME: str = "gemma4:12b"
    LLM_API_BASE: str = "http://localhost:11434"
    LLM_API_KEY: str | None = None
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 8192
    LLM_VALIDATION_MAX_TOKENS: int = 1024
    LLM_SCRIPT_MAX_TOKENS: int = 8192
    LLM_UNLIMITED_OUTPUT: bool = True
    LLM_REQUEST_TIMEOUT: int = 60
    LLM_MAX_RETRIES: int = 3

    # LangGraph pipeline
    IDEA_MIN_SCORE: int = 7
    IDEA_MAX_RETRIES: int = 3
    PIPELINE_STALE_AFTER_MINUTES: int = 30
    PIPELINE_MAX_RETRIES: int = 5
    PIPELINE_CELERY_MAX_RETRIES: int = 5
    PIPELINE_CELERY_RETRY_BACKOFF_MAX: int = 600
    PIPELINE_VISIBILITY_TIMEOUT: int = 3600

    # MoneyPrinterTurbo
    MPT_BASE_URL: str = "http://localhost:8080"
    MPT_API_TOKEN: str | None = None
    MPT_VOICE_NAME_EN: str = "en-US-AriaNeural"
    MPT_REQUEST_TIMEOUT: float = 120.0
    MPT_POLL_INTERVAL: float = 5.0
    MPT_POLL_TIMEOUT: float = 600.0

    # ntfy pipeline notifications (public ntfy.sh or self-hosted URL)
    NTFY_ENABLED: bool = False
    NTFY_BASE_URL: str = "https://ntfy.sh"
    NTFY_TOPIC: str = ""
    NTFY_REQUEST_TIMEOUT: float = 5.0

    # Platform OAuth (app-level; per-channel tokens live in credentials_json)
    YOUTUBE_CLIENT_ID: str | None = None
    YOUTUBE_CLIENT_SECRET: str | None = None
    TIKTOK_CLIENT_KEY: str | None = None
    TIKTOK_CLIENT_SECRET: str | None = None
    TIKTOK_REQUEST_TIMEOUT: float = 120.0
    TIKTOK_POLL_INTERVAL: float = 5.0
    TIKTOK_POLL_TIMEOUT: float = 600.0
    META_APP_ID: str | None = None
    META_APP_SECRET: str | None = None

    # Public base URL for locally stored media (required for Instagram REELS)
    PUBLIC_MEDIA_BASE_URL: str | None = None

    # RSS news feeds
    RSS_ENABLED: bool = True
    RSS_SCRAPE_HOUR: int = 6
    RSS_REQUEST_TIMEOUT: float = 30.0
    RSS_MAX_ITEMS_PER_FEED: int = 50
    RSS_NEWS_MAX_AGE_DAYS: int = 7
    RSS_USER_AGENT: str = "ReelsAutomation-RSS/1.0"


class TestSettings(GlobalSettings):
    DB_SCHEMA: str = f"test_{randint(1, 100_000)}"

    def __init__(self, **kwargs):
        kwargs.setdefault("DB_SCHEMA", f"test_{randint(1, 100_000)}")
        super().__init__(**kwargs)


class DevelopmentSettings(GlobalSettings):
    ALLOWED_ORIGINS: str = "*"


class ProductionSettings(GlobalSettings):
    ALLOWED_ORIGINS: str = "127.0.0.1,localhost,"


def get_settings():
    env = os.environ.get("ENVIRONMENT", "development")

    if env == "test":
        return TestSettings()
    elif env == "development":
        return DevelopmentSettings()
    elif env == "production":
        return ProductionSettings()

    return GlobalSettings()


settings = get_settings()


class TikTokConfig(BaseModel):
    base_url: str = "https://open.tiktokapis.com"
    access_token: str
    request_timeout: float = 120.0
    poll_interval: float = 5.0
    poll_timeout: float = 600.0


def build_tiktok_config(access_token: str) -> TikTokConfig:
    return TikTokConfig(
        access_token=access_token,
        request_timeout=settings.TIKTOK_REQUEST_TIMEOUT,
        poll_interval=settings.TIKTOK_POLL_INTERVAL,
        poll_timeout=settings.TIKTOK_POLL_TIMEOUT,
    )


LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "default": {
            "level": settings.LOG_LEVEL,
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
    },
    "loggers": {
        "": {"handlers": ["default"], "level": settings.LOG_LEVEL, "propagate": False},
        "uvicorn": {
            "handlers": ["default"],
            "level": logging.INFO,
            "propagate": False,
        },
        "httpx": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
        "httpcore": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
