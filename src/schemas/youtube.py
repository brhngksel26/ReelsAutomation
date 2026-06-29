from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class YouTubeCredentials(BaseModel):
    access_token: str
    refresh_token: str
    client_id: str
    client_secret: str
    token_expires_at: datetime | None = None


class YouTubePlatformSettings(BaseModel):
    privacy_status: str = "public"
    category_id: str = "22"


class YouTubeVideoSnippet(BaseModel):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    category_id: str = "22"


class YouTubeUploadRequest(BaseModel):
    snippet: YouTubeVideoSnippet
    privacy_status: str = "public"
    video_path: str


class YouTubeUploadResult(BaseModel):
    video_id: str
    status: str | None = None


class YouTubeVideoStats(BaseModel):
    video_id: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0


class YouTubeComment(BaseModel):
    comment_id: str
    text: str
    author: str | None = None
    published_at: str | None = None


class YouTubeConfig(BaseModel):
    api_base_url: str = "https://www.googleapis.com/youtube/v3"
    upload_base_url: str = "https://www.googleapis.com/upload/youtube/v3"
    oauth_token_url: str = "https://oauth2.googleapis.com/token"
    request_timeout: float = 120.0
    credentials: YouTubeCredentials
