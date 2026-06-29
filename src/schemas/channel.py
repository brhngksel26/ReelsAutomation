from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import SchedulingMode


class ChannelCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    niche: str = Field(min_length=1, max_length=100)
    target_audience: str = Field(min_length=1, max_length=255)
    language: str = Field(min_length=2, max_length=50)
    tone_of_voice: str = Field(min_length=1, max_length=100)
    system_prompt: str = ""
    daily_video_count: int = Field(default=1, ge=1, le=50)
    posting_hours: list[time] = Field(default_factory=list)
    base_hashtags: list[str] = Field(default_factory=list)
    is_active: bool = True
    scheduling_mode: SchedulingMode = SchedulingMode.FIXED_HOURS
    rss_interval_minutes: int = Field(default=30, ge=5, le=1440)
    rss_max_videos_per_day: int = Field(default=20, ge=1, le=50)


class ChannelUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    niche: str | None = Field(default=None, min_length=1, max_length=100)
    target_audience: str | None = Field(default=None, min_length=1, max_length=255)
    language: str | None = Field(default=None, min_length=2, max_length=50)
    tone_of_voice: str | None = Field(default=None, min_length=1, max_length=100)
    system_prompt: str | None = None
    daily_video_count: int | None = Field(default=None, ge=1, le=50)
    posting_hours: list[time] | None = None
    base_hashtags: list[str] | None = None
    is_active: bool | None = None
    scheduling_mode: SchedulingMode | None = None
    rss_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    rss_max_videos_per_day: int | None = Field(default=None, ge=1, le=50)


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    profile_id: int
    name: str
    niche: str
    target_audience: str
    language: str
    tone_of_voice: str
    system_prompt: str
    daily_video_count: int
    posting_hours: list[time]
    base_hashtags: list[str]
    is_active: bool
    scheduling_mode: SchedulingMode
    rss_interval_minutes: int
    rss_max_videos_per_day: int
    rss_last_scheduled_date: date | None = None
