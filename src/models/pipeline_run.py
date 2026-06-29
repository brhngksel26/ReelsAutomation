from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.core.database import metadata
from src.core.enums import PipelineRunStatus


class _PipelineRunBase(DeclarativeBase):
    metadata = metadata


class PipelineRun(_PipelineRunBase):
    __tablename__ = "pipeline_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[PipelineRunStatus] = mapped_column(
        String(20),
        default=PipelineRunStatus.PENDING,
        nullable=False,
        index=True,
    )
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    video_metadata_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("video_metadata.id"),
        nullable=True,
    )
    news_consumption_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("channel_news_consumption.id"),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
