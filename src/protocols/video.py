from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import GenerationStatus, PublishStatus

if TYPE_CHECKING:
    from src.models.video import VideoMetadata, VideoPublishStatus


class VideoMetadataRepository(Protocol):
    async def create(self, db: AsyncSession, data: dict) -> VideoMetadata: ...

    async def get(self, db: AsyncSession, **filters: Any) -> VideoMetadata | None: ...

    async def get_by_id(self, db: AsyncSession, id: int) -> VideoMetadata | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[VideoMetadata]: ...

    async def update(
        self, db: AsyncSession, id: int, data: dict
    ) -> VideoMetadata | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def get_upcoming_by_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[VideoMetadata]: ...

    async def get_with_publish_statuses(
        self,
        db: AsyncSession,
        video_id: int,
    ) -> VideoMetadata | None: ...

    async def get_recent_published_by_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        limit: int = 5,
    ) -> list[VideoMetadata]: ...

    async def get_due_for_publish(self, db: AsyncSession) -> list[VideoMetadata]: ...

    async def update_generation_status(
        self,
        db: AsyncSession,
        video_id: int,
        status: GenerationStatus,
        *,
        video_path: str | None = None,
        audio_path: str | None = None,
    ) -> VideoMetadata | None: ...

    async def get_owned(
        self,
        db: AsyncSession,
        video_id: int,
        profile_id: int,
    ) -> VideoMetadata | None: ...


class VideoPublishStatusRepository(Protocol):
    async def create(self, db: AsyncSession, data: dict) -> VideoPublishStatus: ...

    async def get(
        self, db: AsyncSession, **filters: Any
    ) -> VideoPublishStatus | None: ...

    async def get_by_id(
        self, db: AsyncSession, id: int
    ) -> VideoPublishStatus | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[VideoPublishStatus]: ...

    async def update(
        self, db: AsyncSession, id: int, data: dict
    ) -> VideoPublishStatus | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def get_by_video_id(
        self,
        db: AsyncSession,
        video_id: int,
    ) -> list[VideoPublishStatus]: ...

    async def upsert_for_platform(
        self,
        db: AsyncSession,
        video_id: int,
        platform_type: str,
        publish_status: PublishStatus,
        *,
        platform_video_id: str | None = None,
        error_log: str | None = None,
        published_at: datetime | None = None,
    ) -> VideoPublishStatus: ...

    async def list_failed_for_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        *,
        channel_id: int | None = None,
        limit: int = 100,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]: ...

    async def list_failed_video_ids(self, db: AsyncSession) -> list[int]: ...

    async def list_published_in_window(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]: ...

    async def list_failed_in_window(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]: ...

    async def list_failed_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        limit: int = 100,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]: ...
