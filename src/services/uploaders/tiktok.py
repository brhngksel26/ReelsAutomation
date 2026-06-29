from __future__ import annotations

import logging
from pathlib import Path

from src.core.config import build_tiktok_config
from src.core.enums import PlatformType
from src.integrations.tiktok.client import TikTokClient, TikTokUploadError
from src.models.channel import PlatformConfig
from src.models.video import VideoMetadata
from src.protocols.tiktok import TikTokUploadStrategy
from src.schemas.tiktok import (
    TikTokCredentials,
    TikTokFileSourceInfo,
    TikTokPostInfo,
    TikTokPostMode,
    TikTokUploadResult,
    build_post_info_from_video_metadata,
)
from src.services.uploaders.base import UploadContext, register_uploader

logger = logging.getLogger(__name__)


class DirectPostStrategy:
    async def upload(
        self,
        client: TikTokClient,
        *,
        post_info: TikTokPostInfo,
        video_bytes: bytes,
        video_size: int,
    ) -> TikTokUploadResult:
        source_info = TikTokFileSourceInfo(
            video_size=video_size,
            chunk_size=video_size,
            total_chunk_count=1,
        )
        return await client.upload_direct_post(
            post_info=post_info,
            source_info=source_info,
            video_bytes=video_bytes,
        )


class InboxUploadStrategy:
    async def upload(
        self,
        client: TikTokClient,
        *,
        post_info: TikTokPostInfo,
        video_bytes: bytes,
        video_size: int,
    ) -> TikTokUploadResult:
        del post_info
        source_info = TikTokFileSourceInfo(
            video_size=video_size,
            chunk_size=video_size,
            total_chunk_count=1,
        )
        return await client.upload_inbox(
            source_info=source_info,
            video_bytes=video_bytes,
        )


def _resolve_post_mode(platform_config: PlatformConfig) -> TikTokPostMode:
    raw_mode = platform_config.platform_specific_settings.get(
        "post_mode", "inbox_upload"
    )
    try:
        return TikTokPostMode(raw_mode)
    except ValueError as exc:
        raise TikTokUploadError(f"Unsupported TikTok post_mode: {raw_mode}") from exc


def _resolve_strategy(post_mode: TikTokPostMode) -> TikTokUploadStrategy:
    strategies: dict[TikTokPostMode, TikTokUploadStrategy] = {
        TikTokPostMode.DIRECT_POST: DirectPostStrategy(),
        TikTokPostMode.INBOX_UPLOAD: InboxUploadStrategy(),
    }
    return strategies[post_mode]


def _read_video_bytes(video: VideoMetadata) -> tuple[bytes, int]:
    if not video.video_path:
        raise TikTokUploadError(f"Video {video.id} has no video_path for TikTok upload")
    path = Path(video.video_path)
    if not path.is_file():
        raise TikTokUploadError(f"Video file not found: {video.video_path}")
    video_bytes = path.read_bytes()
    return video_bytes, len(video_bytes)


def _build_client(platform_config: PlatformConfig) -> TikTokClient:
    credentials = TikTokCredentials.model_validate(platform_config.credentials_json)
    config = build_tiktok_config(credentials.access_token)
    return TikTokClient(config)


@register_uploader(PlatformType.TIKTOK.value)
class TikTokUploader:
    async def upload(self, ctx: UploadContext) -> str:
        video = ctx.video
        platform_config = ctx.platform_config

        post_mode = _resolve_post_mode(platform_config)
        strategy = _resolve_strategy(post_mode)
        client = _build_client(platform_config)
        post_info = build_post_info_from_video_metadata(
            hook_text=video.hook_text,
            caption=video.caption,
            hashtags=video.generated_hashtags,
        )
        video_bytes, video_size = _read_video_bytes(video)

        logger.info(
            "Uploading video %s to TikTok via %s",
            video.id,
            post_mode.value,
        )
        result = await strategy.upload(
            client,
            post_info=post_info,
            video_bytes=video_bytes,
            video_size=video_size,
        )
        platform_video_id = result.platform_video_id or result.publish_id
        logger.info(
            "TikTok upload complete for video %s: publish_id=%s platform_video_id=%s",
            video.id,
            result.publish_id,
            platform_video_id,
        )
        return platform_video_id
