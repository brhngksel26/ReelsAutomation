from __future__ import annotations

import logging

from src.core.database import pipeline_async_session_maker
from src.core.deps import get_channel_crud
from src.core.unit_of_work import transaction
from src.integrations.llm_manager import get_llm_manager
from src.integrations.llm_manager.schemas import VideoIdeaOutput
from src.pipeline.exceptions import PipelineChannelNotFoundError, PipelineStateError
from src.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


async def generate_script(state: PipelineState) -> dict:
    channel_id = state["channel_id"]
    idea_payload = state.get("video_idea")
    if not idea_payload:
        raise PipelineStateError("video_idea is required before generate_script")

    idea = VideoIdeaOutput.model_validate(idea_payload)

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            channel = await get_channel_crud().get_by_id(db, channel_id)
            if not channel or channel.is_deleted:
                raise PipelineChannelNotFoundError(channel_id)

            llm = get_llm_manager()
            script = await llm.generate_video_script(channel, idea)

    logger.info("generate_script channel_id=%s title=%s", channel_id, script.title)
    return {
        "video_script": script.model_dump(mode="json"),
        "current_step": "generate_script",
    }
