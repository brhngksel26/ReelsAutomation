from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.models.channel import Channel, PlatformConfig


class ChannelRepository(Protocol):
    async def create(self, db: AsyncSession, data: dict) -> Channel: ...

    async def get(self, db: AsyncSession, **filters: Any) -> Channel | None: ...

    async def get_by_id(self, db: AsyncSession, id: int) -> Channel | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[Channel]: ...

    async def update(self, db: AsyncSession, id: int, data: dict) -> Channel | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def get_by_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Channel]: ...

    async def get_owned(
        self,
        db: AsyncSession,
        channel_id: int,
        profile_id: int,
    ) -> Channel | None: ...

    async def list_active(self, db: AsyncSession) -> list[Channel]: ...


class PlatformConfigRepository(Protocol):
    async def create(self, db: AsyncSession, data: dict) -> PlatformConfig: ...

    async def get(self, db: AsyncSession, **filters: Any) -> PlatformConfig | None: ...

    async def get_by_id(self, db: AsyncSession, id: int) -> PlatformConfig | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[PlatformConfig]: ...

    async def update(
        self, db: AsyncSession, id: int, data: dict
    ) -> PlatformConfig | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def get_by_channel_and_platform(
        self,
        db: AsyncSession,
        channel_id: int,
        platform_type: str,
    ) -> PlatformConfig | None: ...

    async def get_by_profile_channels(
        self,
        db: AsyncSession,
        channel_ids: list[int],
    ) -> list[PlatformConfig]: ...

    async def get_by_channel_id(
        self,
        db: AsyncSession,
        channel_id: int,
    ) -> list[PlatformConfig]: ...
