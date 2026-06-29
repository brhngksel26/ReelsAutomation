from __future__ import annotations

import logging

from src.core.database import pipeline_async_session_maker
from src.core.deps import get_channel_news_consumption_crud
from src.core.unit_of_work import transaction
from src.pipeline.exceptions import PipelineStateError
from src.pipeline.state import PipelineState
from src.services.publishing import publish_video_to_platforms

logger = logging.getLogger(__name__)


async def publish(state: PipelineState) -> dict:
    video_metadata_id = state.get("video_metadata_id")
    if video_metadata_id is None:
        raise PipelineStateError("video_metadata_id is required before publish")

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            publish_results = await publish_video_to_platforms(db, video_metadata_id)
            consumption_id = state.get("news_consumption_id")
            if consumption_id is not None and any(
                result.get("success") for result in publish_results
            ):
                await get_channel_news_consumption_crud().mark_published(
                    db, consumption_id
                )

    logger.info(
        "publish video_metadata_id=%s platform_count=%s",
        video_metadata_id,
        len(publish_results),
    )
    return {
        "publish_results": publish_results,
        "current_step": "publish",
    }
