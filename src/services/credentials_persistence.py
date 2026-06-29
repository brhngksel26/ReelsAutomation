from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.channel import PlatformConfig
from src.protocols.channel import PlatformConfigRepository


def merge_refreshed_youtube_credentials(
    credentials_json: dict,
    access_token: str,
    token_expires_at: datetime | None,
) -> dict:
    updated = {**credentials_json, "access_token": access_token}
    if token_expires_at is not None:
        updated["token_expires_at"] = token_expires_at.isoformat()
    return updated


def build_youtube_token_refresh_callback(
    db: AsyncSession,
    platform_config: PlatformConfig,
    *,
    platform_config_crud: PlatformConfigRepository | None = None,
) -> Callable[[str, datetime | None], Awaitable[None]]:
    from src.core.deps import get_platform_config_crud

    platform_config_crud = platform_config_crud or get_platform_config_crud()

    async def on_refreshed(
        access_token: str, token_expires_at: datetime | None
    ) -> None:
        credentials_json = merge_refreshed_youtube_credentials(
            platform_config.credentials_json,
            access_token,
            token_expires_at,
        )
        await platform_config_crud.update(
            db,
            platform_config.id,
            {"credentials_json": credentials_json},
        )
        platform_config.credentials_json = credentials_json

    return on_refreshed
