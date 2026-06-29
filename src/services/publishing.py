import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import (
    get_platform_config_crud,
    get_video_metadata_crud,
    get_video_publish_status_crud,
)
from src.core.enums import GenerationStatus, PublishStatus
from src.protocols.channel import PlatformConfigRepository
from src.protocols.video import VideoMetadataRepository, VideoPublishStatusRepository
from src.services.uploaders import UPLOADERS  # noqa: F401 — register uploaders
from src.services.uploaders.base import UploadContext, get_uploader

logger = logging.getLogger(__name__)


async def publish_video_to_platforms(
    db: AsyncSession,
    video_metadata_id: int,
    *,
    video_metadata_crud: VideoMetadataRepository | None = None,
    video_publish_status_crud: VideoPublishStatusRepository | None = None,
    platform_config_crud: PlatformConfigRepository | None = None,
) -> list[dict]:
    video_crud = video_metadata_crud or get_video_metadata_crud()
    publish_crud = video_publish_status_crud or get_video_publish_status_crud()
    platform_crud = platform_config_crud or get_platform_config_crud()

    video = await video_crud.get_by_id(db, video_metadata_id)
    if not video:
        logger.warning("Video %s not found for publish", video_metadata_id)
        return []

    if video.generation_status != GenerationStatus.COMPLETED.value:
        logger.info(
            "Video %s not ready for publish (status=%s)",
            video_metadata_id,
            video.generation_status,
        )
        return []

    platform_configs = await platform_crud.get_by_channel_id(db, video.channel_id)
    if not platform_configs:
        logger.info("No platform configs for video %s", video_metadata_id)
        return []

    results: list[dict] = []
    for config in platform_configs:
        platform_type = config.platform_type
        await publish_crud.upsert_for_platform(
            db,
            video_metadata_id,
            platform_type,
            PublishStatus.UPLOADING,
        )
        try:
            uploader = get_uploader(platform_type)
            ctx = UploadContext(video=video, platform_config=config, db=db)
            platform_video_id = await uploader.upload(ctx)
            await publish_crud.upsert_for_platform(
                db,
                video_metadata_id,
                platform_type,
                PublishStatus.PUBLISHED,
                platform_video_id=platform_video_id,
                published_at=datetime.now(timezone.utc),
            )
            logger.info(
                "Published video %s to %s as %s",
                video_metadata_id,
                platform_type,
                platform_video_id,
            )
            result: dict = {
                "platform": platform_type,
                "success": True,
                "platform_video_id": platform_video_id,
            }
            results.append(result)
        except Exception as exc:
            logger.exception(
                "Failed to publish video %s to %s",
                video_metadata_id,
                platform_type,
            )
            await publish_crud.upsert_for_platform(
                db,
                video_metadata_id,
                platform_type,
                PublishStatus.FAILED,
                error_log=str(exc),
            )
            results.append(
                {
                    "platform": platform_type,
                    "success": False,
                    "platform_video_id": None,
                    "error": str(exc),
                }
            )

    return results
