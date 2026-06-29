from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class PublishedVideoDigestItem(BaseModel):
    video_id: int
    hook_text: str
    platform_type: str
    platform_label: str
    platform_url: str | None = None


class FailedPublishDigestItem(BaseModel):
    video_id: int
    hook_text: str
    platform_type: str
    platform_label: str
    error_log: str | None = None


class FailedPipelineDigestItem(BaseModel):
    run_id: str
    last_error: str | None = None
    current_step: str | None = None


class ChannelProfileLink(BaseModel):
    platform_type: str
    platform_label: str
    profile_url: str


class ChannelDigestOut(BaseModel):
    channel_id: int
    channel_name: str
    digest_date: date
    published: list[PublishedVideoDigestItem] = Field(default_factory=list)
    failed_publishes: list[FailedPublishDigestItem] = Field(default_factory=list)
    failed_pipelines: list[FailedPipelineDigestItem] = Field(default_factory=list)
    retry_pending_publishes: int = 0
    retry_pending_pipelines: int = 0
    profile_links: list[ChannelProfileLink] = Field(default_factory=list)
