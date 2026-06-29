from datetime import date

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import BaseModel
from src.core.enums import PlatformStatus, PlatformType, SchedulingMode
from src.models.rss import channel_rss_feeds


class Channel(BaseModel):
    __tablename__ = "channels"

    profile_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profiles.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[str] = mapped_column(String(100), nullable=False)
    target_audience: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    tone_of_voice: Mapped[str] = mapped_column(String(100), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    daily_video_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    posting_hours: Mapped[list] = mapped_column(
        ARRAY(Time), nullable=False, default=list
    )
    base_hashtags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    scheduling_mode: Mapped[SchedulingMode] = mapped_column(
        String(20),
        default=SchedulingMode.FIXED_HOURS,
        nullable=False,
    )
    rss_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    rss_max_videos_per_day: Mapped[int] = mapped_column(
        Integer, default=20, nullable=False
    )
    rss_last_scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    profile: Mapped["Profile"] = relationship("Profile", back_populates="channels")
    platform_configs: Mapped[list["PlatformConfig"]] = relationship(
        "PlatformConfig",
        back_populates="channel",
        lazy="selectin",
    )
    videos: Mapped[list["VideoMetadata"]] = relationship(
        "VideoMetadata",
        back_populates="channel",
        lazy="selectin",
    )
    rss_feeds: Mapped[list["RssFeed"]] = relationship(
        "RssFeed",
        secondary=channel_rss_feeds,
        back_populates="channels",
        lazy="selectin",
    )
    news_consumptions: Mapped[list["ChannelNewsConsumption"]] = relationship(
        "ChannelNewsConsumption",
        back_populates="channel",
        lazy="selectin",
    )


class PlatformConfig(BaseModel):
    __tablename__ = "platform_configs"
    __table_args__ = (
        UniqueConstraint("channel_id", "platform_type", name="uq_channel_platform"),
    )

    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )
    platform_type: Mapped[PlatformType] = mapped_column(String(50), nullable=False)
    credentials_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[PlatformStatus] = mapped_column(
        String(20),
        default=PlatformStatus.CONNECTED,
        nullable=False,
    )
    platform_specific_settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    channel: Mapped["Channel"] = relationship(
        "Channel", back_populates="platform_configs"
    )
