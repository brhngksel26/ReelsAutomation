from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.schemas.platform_models import (
        Comment,
        UploadRequest,
        UploadResult,
        VideoStats,
    )


class PlatformPublisher(Protocol):
    async def upload_video(self, request: UploadRequest) -> UploadResult: ...


class PlatformAnalytics(Protocol):
    async def get_video_stats(self, video_id: str) -> VideoStats: ...


class PlatformEngagement(Protocol):
    async def list_comments(self, video_id: str) -> list[Comment]: ...
