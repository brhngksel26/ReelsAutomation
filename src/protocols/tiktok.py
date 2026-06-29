from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.integrations.tiktok.client import TikTokClient
    from src.schemas.tiktok import TikTokPostInfo, TikTokUploadResult


class TikTokUploadStrategy(Protocol):
    async def upload(
        self,
        client: TikTokClient,
        *,
        post_info: TikTokPostInfo,
        video_bytes: bytes,
        video_size: int,
    ) -> TikTokUploadResult: ...
