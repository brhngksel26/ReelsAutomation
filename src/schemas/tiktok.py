from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TikTokPostMode(str, Enum):
    DIRECT_POST = "direct_post"
    INBOX_UPLOAD = "inbox_upload"


class TikTokSourceType(str, Enum):
    FILE_UPLOAD = "FILE_UPLOAD"
    PULL_FROM_URL = "PULL_FROM_URL"


class TikTokPublishStatus(str, Enum):
    PROCESSING_UPLOAD = "PROCESSING_UPLOAD"
    PROCESSING_DOWNLOAD = "PROCESSING_DOWNLOAD"
    SEND_TO_USER_INBOX = "SEND_TO_USER_INBOX"
    PUBLISH_COMPLETE = "PUBLISH_COMPLETE"
    FAILED = "FAILED"


class TikTokCredentials(BaseModel):
    """Typed credentials stored in PlatformConfig.credentials_json."""

    access_token: str
    open_id: str
    refresh_token: str | None = None
    token_expires_at: str | None = None


class TikTokPostInfo(BaseModel):
    title: str | None = None
    privacy_level: str = "SELF_ONLY"
    disable_duet: bool | None = None
    disable_stitch: bool | None = None
    disable_comment: bool | None = None
    video_cover_timestamp_ms: int | None = None
    brand_content_toggle: bool | None = None
    brand_organic_toggle: bool | None = None
    is_aigc: bool | None = None


class TikTokFileSourceInfo(BaseModel):
    source: Literal[TikTokSourceType.FILE_UPLOAD] = TikTokSourceType.FILE_UPLOAD
    video_size: int
    chunk_size: int
    total_chunk_count: int = 1


class TikTokUrlSourceInfo(BaseModel):
    source: Literal[TikTokSourceType.PULL_FROM_URL] = TikTokSourceType.PULL_FROM_URL
    video_url: str


class TikTokInitResponse(BaseModel):
    publish_id: str
    upload_url: str | None = None


class TikTokStatusResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: TikTokPublishStatus
    fail_reason: str | None = None
    publicly_available_post_id: list[str] = Field(
        default_factory=list,
        validation_alias="publicaly_available_post_id",
    )
    uploaded_bytes: int | None = None
    downloaded_bytes: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            TikTokPublishStatus.PUBLISH_COMPLETE,
            TikTokPublishStatus.SEND_TO_USER_INBOX,
            TikTokPublishStatus.FAILED,
        }

    @property
    def is_success(self) -> bool:
        return self.status in {
            TikTokPublishStatus.PUBLISH_COMPLETE,
            TikTokPublishStatus.SEND_TO_USER_INBOX,
        }


class TikTokVideo(BaseModel):
    id: str
    title: str | None = None
    cover_image_url: str | None = None
    create_time: int | None = None
    video_description: str | None = None
    duration: int | None = None
    height: int | None = None
    width: int | None = None
    share_url: str | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    view_count: int | None = None


class TikTokVideoListResult(BaseModel):
    videos: list[TikTokVideo] = Field(default_factory=list)
    cursor: int | None = None
    has_more: bool = False


class TikTokVideoQueryResult(BaseModel):
    videos: list[TikTokVideo] = Field(default_factory=list)


class TikTokUploadResult(BaseModel):
    publish_id: str
    platform_video_id: str | None = None


def build_post_info_from_video_metadata(
    *,
    hook_text: str,
    caption: str,
    hashtags: list[str],
) -> TikTokPostInfo:
    """Map domain video metadata to TikTok post_info."""
    hashtag_text = " ".join(hashtags)
    parts = [hook_text.strip()]
    if caption.strip():
        parts.append(caption.strip())
    if hashtag_text.strip():
        parts.append(hashtag_text.strip())
    title = "\n".join(parts)
    return TikTokPostInfo(title=title[:2200] if title else None)
