from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReelsPublishParams(BaseModel):
    video_url: str
    caption: str = ""
    media_type: str = "REELS"
    share_to_feed: bool | None = None
    cover_url: str | None = None
    thumb_offset: int | None = None


class MediaContainerResult(BaseModel):
    id: str


class MediaPublishResult(BaseModel):
    id: str


class ResumableUploadSession(BaseModel):
    ig_user_id: str
    upload_url: str
    file_size: int
    mime_type: str = "video/mp4"


class InstagramInsight(BaseModel):
    name: str
    period: str
    values: list[dict[str, Any]] = Field(default_factory=list)
    title: str | None = None
    description: str | None = None


class InstagramInsightsResult(BaseModel):
    media_id: str
    insights: list[InstagramInsight] = Field(default_factory=list)


class InstagramComment(BaseModel):
    id: str
    text: str
    username: str | None = None
    timestamp: str | None = None


class InstagramCommentsResult(BaseModel):
    media_id: str
    comments: list[InstagramComment] = Field(default_factory=list)


class InstagramError(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class InstagramRequestError(InstagramError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: int | None = None,
    ):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class InstagramAuthError(InstagramRequestError):
    pass


class InstagramUploadError(InstagramRequestError):
    pass
