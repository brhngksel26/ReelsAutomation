from datetime import datetime

from pydantic import BaseModel, Field


class UploadRequest(BaseModel):
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy_status: str | None = None
    platform_settings: dict = Field(default_factory=dict)


class UploadResult(BaseModel):
    platform_video_id: str
    status: str = "published"
    raw_response: dict = Field(default_factory=dict)


class VideoStats(BaseModel):
    video_id: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int | None = None
    fetched_at: datetime | None = None


class Comment(BaseModel):
    id: str
    text: str
    author: str | None = None
    created_at: datetime | None = None
    like_count: int = 0
