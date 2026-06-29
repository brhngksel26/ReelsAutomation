from __future__ import annotations

import logging
from collections.abc import Callable

from src.core.enums import PlatformType
from src.integrations.youtube import (
    YouTubeClient,
    build_youtube_config_from_credentials,
)
from src.models.channel import PlatformConfig
from src.models.video import VideoMetadata
from src.schemas.youtube import (
    YouTubePlatformSettings,
    YouTubeUploadRequest,
    YouTubeVideoSnippet,
)
from src.services.credentials_persistence import build_youtube_token_refresh_callback
from src.services.uploaders.base import UploadContext, register_uploader

logger = logging.getLogger(__name__)

SHORTS_TAG = "Shorts"


def _build_snippet(
    video: VideoMetadata, settings: YouTubePlatformSettings
) -> YouTubeVideoSnippet:
    tags = list(video.generated_hashtags)
    normalized_tags = [tag.lstrip("#") for tag in tags]
    if SHORTS_TAG.lower() not in {tag.lower() for tag in normalized_tags}:
        normalized_tags.append(SHORTS_TAG)

    description = video.caption.strip()
    if description and not description.endswith("#Shorts"):
        description = f"{description}\n\n#Shorts"

    return YouTubeVideoSnippet(
        title=video.hook_text[:100],
        description=description,
        tags=normalized_tags[:30],
        category_id=settings.category_id,
    )


@register_uploader(PlatformType.YOUTUBE_SHORTS.value)
class YouTubeShortsUploader:
    def __init__(
        self,
        *,
        client_factory: Callable[[dict], YouTubeClient] | None = None,
    ) -> None:
        self._client_factory = client_factory

    def _resolve_client(self, platform_config: PlatformConfig) -> YouTubeClient:
        if self._client_factory:
            return self._client_factory(platform_config.credentials_json)

        config = build_youtube_config_from_credentials(platform_config.credentials_json)
        return YouTubeClient(config)

    async def upload(self, ctx: UploadContext) -> str:
        video = ctx.video
        platform_config = ctx.platform_config

        if not video.video_path:
            raise ValueError(f"Video {video.id} has no video_path for upload")

        settings = YouTubePlatformSettings.model_validate(
            platform_config.platform_specific_settings or {}
        )
        snippet = _build_snippet(video, settings)
        request = YouTubeUploadRequest(
            snippet=snippet,
            privacy_status=settings.privacy_status,
            video_path=video.video_path,
        )

        client = self._resolve_client(platform_config)
        if ctx.db is not None:
            client.set_token_refreshed_callback(
                build_youtube_token_refresh_callback(ctx.db, platform_config)
            )
        result = await client.upload_video(request)
        logger.info(
            "Uploaded video %s to YouTube Shorts as %s (status=%s)",
            video.id,
            result.video_id,
            result.status,
        )
        return result.video_id
