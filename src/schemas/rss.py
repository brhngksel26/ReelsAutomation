from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RssFeedItem(BaseModel):
    """Parsed RSS entry from a single feed fetch."""

    title: str
    link: str
    guid: str
    summary: str = ""
    author: str = ""
    published_at: datetime | None = None


class RssFetchResult(BaseModel):
    """Result of fetching and parsing one RSS feed URL."""

    feed_url: str
    items: list[RssFeedItem] = Field(default_factory=list)
    error: str | None = None


class RssFeedCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1000)
    category: str = Field(default="general", max_length=100)
    is_active: bool = True


class RssFeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    category: str
    is_active: bool


class RssNewsItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feed_id: int
    title: str
    summary: str
    link: str
    author: str
    published_at: datetime | None
    fetched_at: datetime


class ChannelFeedGrantIn(BaseModel):
    feed_ids: list[int] = Field(min_length=1)


class ChannelNewsConsumptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    news_item_id: int
    video_metadata_id: int | None
    status: str


class RssScheduleOut(BaseModel):
    channel_id: int
    scheduled_videos: int
    interval_minutes: int
