from __future__ import annotations

from pydantic import BaseModel, Field

from src.schemas.pipeline import PipelineRunOut


class RetryablePipelineRunOut(PipelineRunOut):
    retryable: bool = True


class FailedPublishOut(BaseModel):
    video_id: int
    channel_id: int
    platform_type: str
    publish_status: str
    error_log: str | None = None
    hook_text: str
    video_path: str | None = None


class RetryEnqueueOut(BaseModel):
    message: str
    enqueued: int
    skipped: int
    skipped_reasons: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    video_ids: list[int] = Field(default_factory=list)
