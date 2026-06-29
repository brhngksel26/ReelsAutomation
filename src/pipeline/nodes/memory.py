from __future__ import annotations

import logging

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import pipeline_async_session_maker
from src.core.deps import get_channel_crud, get_video_metadata_crud
from src.core.enums import PublishStatus
from src.core.unit_of_work import transaction
from src.models.video import VideoMetadata, VideoPublishStatus
from src.pipeline.state import PipelineState
from src.schemas.pipeline_contract import ChannelContext

logger = logging.getLogger(__name__)

_RECENT_PUBLISHED_LIMIT = 10


async def _fetch_recent_published_by_channel(
    db: AsyncSession,
    channel_id: int,
    *,
    limit: int = _RECENT_PUBLISHED_LIMIT,
) -> list[VideoMetadata]:
    crud = get_video_metadata_crud()
    get_recent = getattr(crud, "get_recent_published_by_channel", None)
    if callable(get_recent):
        return await get_recent(db, channel_id, limit=limit)

    result = await db.execute(
        select(VideoMetadata)
        .join(
            VideoPublishStatus,
            VideoPublishStatus.video_id == VideoMetadata.id,
        )
        .where(
            and_(
                VideoMetadata.channel_id == channel_id,
                VideoMetadata.is_deleted.is_(False),
                VideoPublishStatus.is_deleted.is_(False),
                VideoPublishStatus.publish_status == PublishStatus.PUBLISHED.value,
            )
        )
        .order_by(VideoPublishStatus.published_at.desc())
        .limit(limit)
    )
    return list(result.scalars().unique().all())


def _video_to_context_entry(video: VideoMetadata) -> dict[str, object]:
    return {
        "title": video.hook_text,
        "hook": video.hook_text,
        "hashtags": list(video.generated_hashtags or []),
    }


async def memory_enrichment(state: PipelineState) -> dict:
    channel_id = state["channel_id"]
    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            channel = await get_channel_crud().get_by_id(db, channel_id)
            if channel is None or channel.is_deleted:
                channel_context = None
            else:
                channel_context = ChannelContext.from_channel(channel).model_dump(
                    mode="json"
                )

            recent_videos = await _fetch_recent_published_by_channel(db, channel_id)
            past_performance = [
                _video_to_context_entry(video) for video in recent_videos
            ]

    logger.info(
        "memory_enrichment channel_id=%s recent_count=%s",
        channel_id,
        len(past_performance),
    )
    return {
        "channel_context": channel_context,
        "past_performance": past_performance,
        "current_step": "memory_enrichment",
    }
