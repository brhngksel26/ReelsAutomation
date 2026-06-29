import os
import random

os.environ["ENVIRONMENT"] = "test"
os.environ["DB_SCHEMA"] = f"test_{random.randint(1, 100_000)}"
# Host tests reach Postgres via published port; .env may use the Docker service name.
os.environ.setdefault("DB_HOST", "localhost")

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.api.deps import (
    get_auth_permission_crud,
    get_channel_crud,
    get_channel_news_consumption_crud,
    get_pipeline_run_crud,
    get_platform_config_crud,
    get_profile_crud,
    get_rss_feed_crud,
    get_rss_news_item_crud,
    get_user_crud,
    get_video_metadata_crud,
    get_video_publish_status_crud,
)
from src.core.celery_app import celery_app
from src.core.config import settings
from src.core.database import BaseModel, get_async_session, sync_engine
from src.core.permission import DEFAULT_FREE_TIER_PERMISSIONS
from src.main import app

# Registry of API-layer CRUD dependency callables (src.api.deps → core.deps factories).
# Integration tests use real CRUD instances by default; override via crud_overrides fixture.
API_CRUD_DEPS: dict[Callable[[], Any], str] = {
    get_auth_permission_crud: "AuthPermissionCrud",
    get_channel_crud: "ChannelCrud",
    get_channel_news_consumption_crud: "ChannelNewsConsumptionCrud",
    get_pipeline_run_crud: "PipelineRunCrud",
    get_platform_config_crud: "PlatformConfigCrud",
    get_profile_crud: "ProfileCrud",
    get_rss_feed_crud: "RssFeedCrud",
    get_rss_news_item_crud: "RssNewsItemCrud",
    get_user_crud: "UserCrud",
    get_video_metadata_crud: "VideoMetadataCrud",
    get_video_publish_status_crud: "VideoPublishStatusCrud",
}

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

_db_url = (
    settings.DB_URL
    or f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)
test_engine = create_async_engine(_db_url, poolclass=NullPool)
test_session_maker = sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_policy().new_event_loop()
    yield loop
    loop.close()


def _seed_permissions_sync() -> None:
    with sync_engine.connect() as conn:
        existing = conn.execute(
            text(f'SELECT 1 FROM "{settings.DB_SCHEMA}".permissions LIMIT 1')
        ).first()
        if existing:
            return
        for perm in DEFAULT_FREE_TIER_PERMISSIONS:
            conn.execute(
                text(
                    f'INSERT INTO "{settings.DB_SCHEMA}".permissions '
                    "(name, description, permission, is_deleted) "
                    "VALUES (:name, :description, :permission, false)"
                ),
                {
                    "name": perm.value.replace(":", "_"),
                    "description": perm.value,
                    "permission": perm.value,
                },
            )
        conn.commit()


@pytest.fixture(autouse=True)
def mock_celery_delay(request, monkeypatch):
    if "test_celery" in request.node.nodeid:
        return
    mock = MagicMock()
    monkeypatch.setattr("src.tasks.video.generate_video_content_task.delay", mock)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    schema = settings.DB_SCHEMA
    with sync_engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        conn.commit()
    BaseModel.metadata.create_all(bind=sync_engine)
    _seed_permissions_sync()
    yield
    BaseModel.metadata.drop_all(bind=sync_engine)
    with sync_engine.connect() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        conn.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_maker() as session:
        yield session


@pytest.fixture
def crud_overrides() -> dict[Callable[[], Any], Callable[[], Any]]:
    """Mutable registry for API CRUD dependency overrides.

    Populate before ``client`` is resolved (via a dependent fixture or
    ``@pytest.mark.usefixtures``) to inject mocks/stubs into route handlers.

    Example — mock channel CRUD for one test::

        @pytest.fixture
        def mock_channel_crud(crud_overrides):
            from unittest.mock import AsyncMock
            from src.cruds.channel import ChannelCrud

            mock = AsyncMock(spec=ChannelCrud)
            crud_overrides[get_channel_crud] = lambda: mock
            return mock

        @pytest.mark.usefixtures("mock_channel_crud")
        async def test_list_channels_empty(client, mock_channel_crud):
            mock_channel_crud.get_by_profile_id.return_value = []
            response = await client.get("/api/v1/channels", headers=auth_headers)
            assert response.status_code == 200

    Direct DB setup in integration tests may still use ``ChannelCrud()`` etc.;
    only HTTP routes resolve dependencies through ``app.dependency_overrides``.
    """
    return {}


def _apply_crud_overrides(
    overrides: dict[Callable[[], Any], Callable[[], Any]],
) -> None:
    for dep, factory in overrides.items():
        app.dependency_overrides[dep] = factory


@pytest_asyncio.fixture
async def client(
    crud_overrides: dict[Callable[[], Any], Callable[[], Any]],
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_async_session():
        async with test_session_maker() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[get_async_session] = override_get_async_session
    _apply_crud_overrides(crud_overrides)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = f"test_{datetime.now(timezone.utc).timestamp()}@example.com"
    password = "securepass123"
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "T",
            "last_name": "U",
        },
    )
    assert reg.status_code == 201
    login = await client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
