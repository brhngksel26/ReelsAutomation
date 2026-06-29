from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class PipelineState(TypedDict, total=False):
    channel_id: int
    channel_context: dict[str, Any] | None
    past_performance: list[dict[str, Any]]
    video_idea: dict[str, Any] | None
    video_script: dict[str, Any] | None
    idea_is_acceptable: bool
    idea_score: int
    video_metadata_id: int | None
    video_path: str | None
    publish_results: list[dict[str, Any]]
    retry_count: int
    current_step: str
    errors: Annotated[list[str], operator.add]
    run_id: str
    selected_news_item: dict[str, Any] | None
    news_required: bool
    news_consumption_id: int | None
