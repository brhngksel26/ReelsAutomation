from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Protocol

from pydantic import BaseModel


class TokenCredentials(BaseModel):
    access_token: str
    token_expires_at: datetime


class TokenRefresher(Protocol):
    async def refresh(self, credentials: TokenCredentials) -> TokenCredentials: ...


def is_token_expired(
    token_expires_at: datetime | None,
    *,
    skew_seconds: int = 60,
) -> bool:
    if token_expires_at is None:
        return False
    now = datetime.now(timezone.utc)
    expires_at = token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return (expires_at - now).total_seconds() <= skew_seconds


async def ensure_valid_token(
    credentials: TokenCredentials,
    refresher: TokenRefresher | None = None,
    *,
    on_refreshed: Callable[[TokenCredentials], Awaitable[None]] | None = None,
) -> TokenCredentials:
    if not is_token_expired(credentials.token_expires_at):
        return credentials

    if refresher is None:
        return credentials

    refreshed = await refresher.refresh(credentials)
    if on_refreshed is not None:
        await on_refreshed(refreshed)
    return refreshed
