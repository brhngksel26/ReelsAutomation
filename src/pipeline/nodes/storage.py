from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.core.database import pipeline_async_session_maker
from src.core.deps import (
    get_channel_news_consumption_crud,
    get_pipeline_run_crud,
    get_video_metadata_crud,
)
from src.core.enums import GenerationStatus
from src.core.unit_of_work import transaction
from src.integrations.llm_manager.schemas import VideoIdeaOutput, VideoScriptOutput
from src.pipeline.exceptions import PipelineStateError
from src.pipeline.state import PipelineState
from src.schemas.pipeline_contract import ChannelContext, merge_hashtags

logger = logging.getLogger(__name__)


async def _lookup_registry_video_metadata_id(run_id: str) -> int | None:
    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            run = await get_pipeline_run_crud().get_by_id(db, run_id)
            if run is None:
                return None
            return getattr(run, "video_metadata_id", None)


async def persist_metadata(state: PipelineState) -> dict:
    channel_id = state["channel_id"]
    existing_id = state.get("video_metadata_id")
    if existing_id is not None:
        logger.info(
            "persist_metadata skip duplicate channel_id=%s video_metadata_id=%s",
            channel_id,
            existing_id,
        )
        return {
            "video_metadata_id": existing_id,
            "current_step": "persist_metadata",
        }

    run_id = state.get("run_id")
    if run_id is not None:
        registry_video_id = await _lookup_registry_video_metadata_id(run_id)
        if registry_video_id is not None:
            logger.info(
                "persist_metadata reuse registry channel_id=%s run_id=%s video_metadata_id=%s",
                channel_id,
                run_id,
                registry_video_id,
            )
            return {
                "video_metadata_id": registry_video_id,
                "current_step": "persist_metadata",
            }

    idea_payload = state.get("video_idea")
    script_payload = state.get("video_script")
    if not idea_payload or not script_payload:
        raise PipelineStateError(
            "video_idea and video_script are required before persist_metadata"
        )

    idea = VideoIdeaOutput.model_validate(idea_payload)
    script = VideoScriptOutput.model_validate(script_payload)
    caption = script.voiceover_text.strip() or idea.hook

    channel_context_payload = state.get("channel_context")
    base_hashtags: list[str] = []
    if channel_context_payload:
        channel_context = ChannelContext.model_validate(channel_context_payload)
        base_hashtags = channel_context.base_hashtags
    hashtags = merge_hashtags(list(script.hashtags or []), base_hashtags)

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            video = await get_video_metadata_crud().create(
                db,
                {
                    "channel_id": channel_id,
                    "hook_text": idea.hook,
                    "caption": caption,
                    "generated_hashtags": hashtags,
                    "scheduled_at": datetime.now(timezone.utc),
                    "generation_status": GenerationStatus.PENDING.value,
                },
            )
            consumption_id = state.get("news_consumption_id")
            if consumption_id is not None:
                await get_channel_news_consumption_crud().attach_video(
                    db,
                    consumption_id,
                    video.id,
                )

    logger.info(
        "persist_metadata channel_id=%s video_metadata_id=%s",
        channel_id,
        video.id,
    )
    return {
        "video_metadata_id": video.id,
        "current_step": "persist_metadata",
    }
