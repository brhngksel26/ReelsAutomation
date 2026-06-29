from datetime import datetime

from sqlalchemy import (
    ARRAY,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import BaseModel
from src.core.enums import GenerationStatus, PlatformType, PublishStatus


class VideoMetadata(BaseModel):
    __tablename__ = "video_metadata"

    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )
    hook_text: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_hashtags: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        default=list,
    )
    video_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    generation_status: Mapped[GenerationStatus] = mapped_column(
        String(20),
        default=GenerationStatus.PENDING,
        nullable=False,
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    channel: Mapped["Channel"] = relationship("Channel", back_populates="videos")
    publish_statuses: Mapped[list["VideoPublishStatus"]] = relationship(
        "VideoPublishStatus",
        back_populates="video",
        lazy="selectin",
    )


class VideoPublishStatus(BaseModel):
    __tablename__ = "video_publish_statuses"
    __table_args__ = (
        UniqueConstraint("video_id", "platform_type", name="uq_video_platform"),
    )

    video_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("video_metadata.id"),
        nullable=False,
        index=True,
    )
    platform_type: Mapped[PlatformType] = mapped_column(String(50), nullable=False)
    publish_status: Mapped[PublishStatus] = mapped_column(
        String(20),
        default=PublishStatus.SCHEDULED,
        nullable=False,
    )
    platform_video_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    video: Mapped["VideoMetadata"] = relationship(
        "VideoMetadata",
        back_populates="publish_statuses",
    )
