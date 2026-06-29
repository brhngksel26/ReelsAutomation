from __future__ import annotations

from typing import Literal

from src.core.config import settings
from src.pipeline.state import PipelineState

IdeaRoute = Literal["continue", "retry", "reject"]
NewsRoute = Literal["continue", "skip"]


def news_availability_router(state: PipelineState) -> NewsRoute:
    news_required = state.get("news_required", False)
    selected_news_item = state.get("selected_news_item")

    if news_required and not selected_news_item:
        return "skip"

    return "continue"


def idea_quality_router(state: PipelineState) -> IdeaRoute:
    score = state.get("idea_score", 0)
    is_acceptable = state.get("idea_is_acceptable", False)
    retry_count = state.get("retry_count", 0)

    if is_acceptable and score >= settings.IDEA_MIN_SCORE:
        return "continue"

    if retry_count < settings.IDEA_MAX_RETRIES:
        return "retry"

    return "reject"
