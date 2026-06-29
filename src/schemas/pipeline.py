from datetime import datetime

from pydantic import BaseModel, Field


class PipelineTriggerIn(BaseModel):
    channel_id: int = Field(gt=0)


class PipelineTriggerOut(BaseModel):
    message: str
    task_id: str
    run_id: str | None = None


class PipelineStatusOut(BaseModel):
    current_step: str | None = None
    retry_count: int | None = None
    errors: list[str] | None = None
    publish_results: list[dict] | None = None


class PipelineRunOut(BaseModel):
    id: str
    channel_id: int
    thread_id: str
    status: str
    current_step: str | None = None
    celery_task_id: str | None = None
    video_metadata_id: int | None = None
    news_consumption_id: int | None = None
    retry_count: int
    last_error: str | None = None
    started_at: datetime | None = None
    updated_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}
