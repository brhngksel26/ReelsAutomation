from __future__ import annotations

import logging
from typing import Any

from src.core.enums import PlatformType
from src.integrations.instagram.config import build_instagram_client_from_credentials
from src.models.video import VideoMetadata
from src.schemas.instagram import InstagramUploadError
from src.services.media_url import resolve_public_video_url
from src.services.uploaders.base import UploadContext, register_uploader

logger = logging.getLogger(__name__)


def build_instagram_caption(video: VideoMetadata) -> str:
    parts: list[str] = []
    if video.caption:
        parts.append(video.caption)
    if video.generated_hashtags:
        parts.append(" ".join(video.generated_hashtags))
    return "\n\n".join(parts)


@register_uploader(PlatformType.INSTAGRAM.value)
class InstagramUploader:
    async def upload(self, ctx: UploadContext) -> str:
        video = ctx.video
        platform_config = ctx.platform_config

        video_url = resolve_public_video_url(video.video_path)
        if not video_url:
            raise InstagramUploadError(
                "Instagram requires a publicly accessible video URL in video_path "
                "(http/https URL or configure PUBLIC_MEDIA_BASE_URL for local paths)"
            )

        settings: dict[str, Any] = platform_config.platform_specific_settings or {}
        media_type = settings.get("media_type", "REELS")
        share_to_feed = settings.get("share_to_feed")

        client = build_instagram_client_from_credentials(
            platform_config.credentials_json
        )
        caption = build_instagram_caption(video)

        logger.info(
            "Publishing Instagram %s for video %s to ig_user_id=%s",
            media_type,
            video.id,
            client.config.ig_user_id,
        )

        return await client.publish_reels(
            video_url=video_url,
            caption=caption,
            media_type=media_type,
            share_to_feed=share_to_feed,
        )
