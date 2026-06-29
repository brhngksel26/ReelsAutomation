from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import BaseModel, metadata
from src.core.enums import NewsConsumptionStatus

channel_rss_feeds = Table(
    "channel_rss_feeds",
    metadata,
    Column("channel_id", Integer, ForeignKey("channels.id"), primary_key=True),
    Column("feed_id", Integer, ForeignKey("rss_feeds.id"), primary_key=True),
)


class RssFeed(BaseModel):
    __tablename__ = "rss_feeds"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_scrape_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_scrape_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    news_items: Mapped[list["RssNewsItem"]] = relationship(
        "RssNewsItem",
        back_populates="feed",
        lazy="selectin",
    )
    channels: Mapped[list["Channel"]] = relationship(
        "Channel",
        secondary=channel_rss_feeds,
        back_populates="rss_feeds",
    )


class RssNewsItem(BaseModel):
    __tablename__ = "rss_news_items"
    __table_args__ = (UniqueConstraint("feed_id", "guid", name="uq_rss_feed_guid"),)

    feed_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rss_feeds.id"),
        nullable=False,
        index=True,
    )
    guid: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    link: Mapped[str] = mapped_column(String(1000), nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    feed: Mapped["RssFeed"] = relationship("RssFeed", back_populates="news_items")
    consumptions: Mapped[list["ChannelNewsConsumption"]] = relationship(
        "ChannelNewsConsumption",
        back_populates="news_item",
        lazy="selectin",
    )


class ChannelNewsConsumption(BaseModel):
    __tablename__ = "channel_news_consumption"
    __table_args__ = (
        UniqueConstraint("channel_id", "news_item_id", name="uq_channel_news_item"),
    )

    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )
    news_item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("rss_news_items.id"),
        nullable=False,
        index=True,
    )
    video_metadata_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("video_metadata.id"),
        nullable=True,
    )
    status: Mapped[NewsConsumptionStatus] = mapped_column(
        String(20),
        default=NewsConsumptionStatus.SELECTED,
        nullable=False,
    )

    channel: Mapped["Channel"] = relationship(
        "Channel", back_populates="news_consumptions"
    )
    news_item: Mapped["RssNewsItem"] = relationship(
        "RssNewsItem",
        back_populates="consumptions",
    )
