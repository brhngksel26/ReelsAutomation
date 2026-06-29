from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.channel import Channel
    from src.models.rss import ChannelNewsConsumption, RssFeed, RssNewsItem
    from src.schemas.rss import RssFeedItem


class RssFeedRepository(Protocol):
    async def create(self, db: AsyncSession, data: dict[str, Any]) -> RssFeed: ...

    async def get(self, db: AsyncSession, **filters: Any) -> RssFeed | None: ...

    async def get_by_id(self, db: AsyncSession, id: int) -> RssFeed | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[RssFeed]: ...

    async def update(
        self, db: AsyncSession, id: int, data: dict[str, Any]
    ) -> RssFeed | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def list_active(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RssFeed]: ...

    async def get_by_url(self, db: AsyncSession, url: str) -> RssFeed | None: ...

    async def get_channel_feed_ids(
        self, db: AsyncSession, channel_id: int
    ) -> list[int]: ...

    async def grant_feeds_to_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        feed_ids: list[int],
    ) -> None: ...

    async def revoke_feed_from_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        feed_id: int,
    ) -> bool: ...

    async def get_channel_with_feeds(
        self,
        db: AsyncSession,
        channel_id: int,
    ) -> Channel | None: ...

    async def list_rss_news_channels(self, db: AsyncSession) -> list[Channel]: ...


class RssNewsItemRepository(Protocol):
    async def create(self, db: AsyncSession, data: dict[str, Any]) -> RssNewsItem: ...

    async def get(self, db: AsyncSession, **filters: Any) -> RssNewsItem | None: ...

    async def get_by_id(self, db: AsyncSession, id: int) -> RssNewsItem | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[RssNewsItem]: ...

    async def update(
        self, db: AsyncSession, id: int, data: dict[str, Any]
    ) -> RssNewsItem | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def upsert_item(
        self,
        db: AsyncSession,
        feed_id: int,
        item: RssFeedItem,
        *,
        fetched_at: datetime | None = None,
    ) -> RssNewsItem | None: ...

    async def get_unused_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        max_age_days: int | None = None,
        limit: int = 1,
    ) -> list[RssNewsItem]: ...

    async def claim_next_news_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        max_age_days: int | None = None,
    ) -> tuple[RssNewsItem, ChannelNewsConsumption] | None: ...

    async def count_unused_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        max_age_days: int | None = None,
    ) -> int: ...

    async def list_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[RssNewsItem]: ...


class ChannelNewsConsumptionRepository(Protocol):
    async def create(
        self, db: AsyncSession, data: dict[str, Any]
    ) -> ChannelNewsConsumption: ...

    async def get(
        self, db: AsyncSession, **filters: Any
    ) -> ChannelNewsConsumption | None: ...

    async def get_by_id(
        self, db: AsyncSession, id: int
    ) -> ChannelNewsConsumption | None: ...

    async def get_many(
        self, db: AsyncSession, skip: int = 0, limit: int = 100, **filters: Any
    ) -> list[ChannelNewsConsumption]: ...

    async def update(
        self, db: AsyncSession, id: int, data: dict[str, Any]
    ) -> ChannelNewsConsumption | None: ...

    async def delete(self, db: AsyncSession, id: int) -> bool: ...

    async def hard_delete(self, db: AsyncSession, id: int) -> bool: ...

    async def count(self, db: AsyncSession, **filters: Any) -> int: ...

    async def mark_selected(
        self,
        db: AsyncSession,
        channel_id: int,
        news_item_id: int,
    ) -> ChannelNewsConsumption: ...

    async def attach_video(
        self,
        db: AsyncSession,
        consumption_id: int,
        video_metadata_id: int,
    ) -> ChannelNewsConsumption | None: ...

    async def mark_published(
        self,
        db: AsyncSession,
        consumption_id: int,
    ) -> ChannelNewsConsumption | None: ...

    async def release_consumption(
        self,
        db: AsyncSession,
        consumption_id: int,
    ) -> bool: ...
