from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import GenerationStatus, PlatformType, PublishStatus


class VideoScheduleIn(BaseModel):
    channel_id: int
    hook_text: str = Field(min_length=1, max_length=500)
    caption: str = ""
    generated_hashtags: list[str] = Field(default_factory=list)
    scheduled_at: datetime


class PublishStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform_type: PlatformType
    publish_status: PublishStatus
    platform_video_id: str | None
    error_log: str | None
    published_at: datetime | None


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    hook_text: str
    caption: str
    generated_hashtags: list[str]
    video_path: str | None
    audio_path: str | None
    generation_status: GenerationStatus
    scheduled_at: datetime


class VideoStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    hook_text: str
    generation_status: GenerationStatus
    scheduled_at: datetime
    publish_statuses: list[PublishStatusOut]
