from __future__ import annotations

import logging

from src.core.config import settings
from src.core.database import pipeline_async_session_maker
from src.core.deps import get_channel_crud
from src.core.unit_of_work import transaction
from src.integrations.llm_manager import get_llm_manager
from src.integrations.llm_manager.prompts.idea_validation import (
    build_idea_validation_prompt,
)
from src.integrations.llm_manager.provider import resolve_output_max_tokens
from src.integrations.llm_manager.schemas import IdeaValidation, VideoIdeaOutput
from src.pipeline.exceptions import PipelineChannelNotFoundError, PipelineStateError
from src.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


async def generate_idea(state: PipelineState) -> dict:
    channel_id = state["channel_id"]
    recent_context = state.get("past_performance") or []
    news_item = state.get("selected_news_item")

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            channel = await get_channel_crud().get_by_id(db, channel_id)
            if not channel or channel.is_deleted:
                raise PipelineChannelNotFoundError(channel_id)

            llm = get_llm_manager()
            idea = await llm.generate_video_idea(
                channel,
                recent_context=recent_context,
                news_item=news_item,
            )

    logger.info("generate_idea channel_id=%s title=%s", channel_id, idea.title)
    return {
        "video_idea": idea.model_dump(mode="json"),
        "current_step": "generate_idea",
    }


async def validate_idea(state: PipelineState) -> dict:
    channel_id = state["channel_id"]
    idea_payload = state.get("video_idea")
    if not idea_payload:
        raise PipelineStateError("video_idea is required before validate_idea")

    idea = VideoIdeaOutput.model_validate(idea_payload)
    retry_count = state.get("retry_count", 0)

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            channel = await get_channel_crud().get_by_id(db, channel_id)
            if not channel or channel.is_deleted:
                raise PipelineChannelNotFoundError(channel_id)

            system_prompt, user_prompt = build_idea_validation_prompt(channel, idea)
            llm = get_llm_manager()
            validation = await llm.complete_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=IdeaValidation,
                temperature=0.5,
                max_tokens=resolve_output_max_tokens(
                    settings.LLM_VALIDATION_MAX_TOKENS
                ),
            )

    passed = validation.is_acceptable and validation.score >= settings.IDEA_MIN_SCORE
    updates: dict = {
        "idea_is_acceptable": passed,
        "idea_score": validation.score,
        "current_step": "validate_idea",
    }
    if not passed:
        updates["retry_count"] = retry_count + 1
        updates["errors"] = [
            f"Idea rejected (score={validation.score}): {validation.reason}"
        ]

    logger.info(
        "validate_idea channel_id=%s score=%s acceptable=%s",
        channel_id,
        validation.score,
        validation.is_acceptable,
    )
    return updates
