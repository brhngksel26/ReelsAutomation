from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.base_crud import BaseCrudService
from src.core.config import settings
from src.core.enums import NewsConsumptionStatus, SchedulingMode
from src.models.channel import Channel
from src.models.rss import (
    ChannelNewsConsumption,
    RssFeed,
    RssNewsItem,
    channel_rss_feeds,
)
from src.schemas.rss import RssFeedItem


class RssFeedCrud(BaseCrudService):
    def __init__(self) -> None:
        super().__init__(RssFeed)

    async def list_active(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RssFeed]:
        result = await db.execute(
            select(RssFeed)
            .where(
                and_(
                    RssFeed.is_active.is_(True),
                    RssFeed.is_deleted.is_(False),
                )
            )
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_url(self, db: AsyncSession, url: str) -> RssFeed | None:
        result = await db.execute(
            select(RssFeed).where(
                and_(
                    RssFeed.url == url,
                    RssFeed.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_channel_feed_ids(
        self, db: AsyncSession, channel_id: int
    ) -> list[int]:
        result = await db.execute(
            select(channel_rss_feeds.c.feed_id).where(
                channel_rss_feeds.c.channel_id == channel_id
            )
        )
        return list(result.scalars().all())

    async def grant_feeds_to_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        feed_ids: list[int],
    ) -> None:
        if not feed_ids:
            return
        existing = set(await self.get_channel_feed_ids(db, channel_id))
        new_ids = [feed_id for feed_id in feed_ids if feed_id not in existing]
        for feed_id in new_ids:
            await db.execute(
                insert(channel_rss_feeds).values(
                    channel_id=channel_id,
                    feed_id=feed_id,
                )
            )
        if new_ids:
            await db.flush()

    async def revoke_feed_from_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        feed_id: int,
    ) -> bool:
        result = await db.execute(
            delete(channel_rss_feeds).where(
                and_(
                    channel_rss_feeds.c.channel_id == channel_id,
                    channel_rss_feeds.c.feed_id == feed_id,
                )
            )
        )
        await db.flush()
        return result.rowcount > 0

    async def get_channel_with_feeds(
        self,
        db: AsyncSession,
        channel_id: int,
    ) -> Channel | None:
        result = await db.execute(
            select(Channel)
            .options(selectinload(Channel.rss_feeds))
            .where(
                and_(
                    Channel.id == channel_id,
                    Channel.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_rss_news_channels(self, db: AsyncSession) -> list[Channel]:
        result = await db.execute(
            select(Channel)
            .join(channel_rss_feeds, Channel.id == channel_rss_feeds.c.channel_id)
            .where(
                and_(
                    Channel.scheduling_mode == SchedulingMode.RSS_NEWS.value,
                    Channel.is_active.is_(True),
                    Channel.is_deleted.is_(False),
                )
            )
            .distinct()
        )
        return list(result.scalars().all())


class RssNewsItemCrud(BaseCrudService):
    def __init__(self) -> None:
        super().__init__(RssNewsItem)

    async def upsert_item(
        self,
        db: AsyncSession,
        feed_id: int,
        item: RssFeedItem,
        *,
        fetched_at: datetime | None = None,
    ) -> RssNewsItem | None:
        fetched_at = fetched_at or datetime.now(timezone.utc)
        existing = await db.execute(
            select(RssNewsItem).where(
                and_(
                    RssNewsItem.feed_id == feed_id,
                    RssNewsItem.guid == item.guid,
                    RssNewsItem.is_deleted.is_(False),
                )
            )
        )
        if existing.scalar_one_or_none():
            return None

        return await self.create(
            db,
            {
                "feed_id": feed_id,
                "guid": item.guid,
                "title": item.title[:500],
                "summary": item.summary,
                "link": item.link[:1000],
                "author": item.author[:255],
                "published_at": item.published_at,
                "fetched_at": fetched_at,
            },
        )

    async def get_unused_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        max_age_days: int | None = None,
        limit: int = 1,
    ) -> list[RssNewsItem]:
        feed_ids = await RssFeedCrud().get_channel_feed_ids(db, channel_id)
        if not feed_ids:
            return []

        max_age_days = (
            max_age_days if max_age_days is not None else settings.RSS_NEWS_MAX_AGE_DAYS
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        consumed_subq = (
            select(ChannelNewsConsumption.news_item_id)
            .where(ChannelNewsConsumption.channel_id == channel_id)
            .where(ChannelNewsConsumption.is_deleted.is_(False))
        )

        query = (
            select(RssNewsItem)
            .where(
                and_(
                    RssNewsItem.feed_id.in_(feed_ids),
                    RssNewsItem.is_deleted.is_(False),
                    RssNewsItem.id.not_in(consumed_subq),
                )
            )
            .order_by(
                RssNewsItem.published_at.desc().nullslast(), RssNewsItem.id.desc()
            )
            .limit(limit)
        )
        if max_age_days > 0:
            query = query.where(
                (RssNewsItem.published_at.is_(None))
                | (RssNewsItem.published_at >= cutoff)
            )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def claim_next_news_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        max_age_days: int | None = None,
    ) -> tuple[RssNewsItem, ChannelNewsConsumption] | None:
        """Atomically select and claim the next unused news item for a channel."""
        feed_ids = await RssFeedCrud().get_channel_feed_ids(db, channel_id)
        if not feed_ids:
            return None

        max_age_days = (
            max_age_days if max_age_days is not None else settings.RSS_NEWS_MAX_AGE_DAYS
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        consumed_subq = (
            select(ChannelNewsConsumption.news_item_id)
            .where(ChannelNewsConsumption.channel_id == channel_id)
            .where(ChannelNewsConsumption.is_deleted.is_(False))
        )

        query = (
            select(RssNewsItem)
            .where(
                and_(
                    RssNewsItem.feed_id.in_(feed_ids),
                    RssNewsItem.is_deleted.is_(False),
                    RssNewsItem.id.not_in(consumed_subq),
                )
            )
            .order_by(
                RssNewsItem.published_at.desc().nullslast(), RssNewsItem.id.desc()
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if max_age_days > 0:
            query = query.where(
                (RssNewsItem.published_at.is_(None))
                | (RssNewsItem.published_at >= cutoff)
            )

        result = await db.execute(query)
        news_item = result.scalar_one_or_none()
        if not news_item:
            return None

        consumption = ChannelNewsConsumption(
            channel_id=channel_id,
            news_item_id=news_item.id,
            status=NewsConsumptionStatus.SELECTED.value,
        )
        db.add(consumption)
        await db.flush()
        await db.refresh(consumption)
        return news_item, consumption

    async def count_unused_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        max_age_days: int | None = None,
    ) -> int:
        feed_ids = await RssFeedCrud().get_channel_feed_ids(db, channel_id)
        if not feed_ids:
            return 0

        max_age_days = (
            max_age_days if max_age_days is not None else settings.RSS_NEWS_MAX_AGE_DAYS
        )
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        consumed_subq = (
            select(ChannelNewsConsumption.news_item_id)
            .where(ChannelNewsConsumption.channel_id == channel_id)
            .where(ChannelNewsConsumption.is_deleted.is_(False))
        )

        query = (
            select(func.count())
            .select_from(RssNewsItem)
            .where(
                and_(
                    RssNewsItem.feed_id.in_(feed_ids),
                    RssNewsItem.is_deleted.is_(False),
                    RssNewsItem.id.not_in(consumed_subq),
                )
            )
        )
        if max_age_days > 0:
            query = query.where(
                (RssNewsItem.published_at.is_(None))
                | (RssNewsItem.published_at >= cutoff)
            )

        result = await db.execute(query)
        return int(result.scalar_one())

    async def list_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[RssNewsItem]:
        feed_ids = await RssFeedCrud().get_channel_feed_ids(db, channel_id)
        if not feed_ids:
            return []
        result = await db.execute(
            select(RssNewsItem)
            .where(
                and_(
                    RssNewsItem.feed_id.in_(feed_ids),
                    RssNewsItem.is_deleted.is_(False),
                )
            )
            .order_by(RssNewsItem.published_at.desc().nullslast())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())


class ChannelNewsConsumptionCrud(BaseCrudService):
    def __init__(self) -> None:
        super().__init__(ChannelNewsConsumption)

    async def mark_selected(
        self,
        db: AsyncSession,
        channel_id: int,
        news_item_id: int,
    ) -> ChannelNewsConsumption:
        return await self.create(
            db,
            {
                "channel_id": channel_id,
                "news_item_id": news_item_id,
                "status": NewsConsumptionStatus.SELECTED.value,
            },
        )

    async def attach_video(
        self,
        db: AsyncSession,
        consumption_id: int,
        video_metadata_id: int,
    ) -> ChannelNewsConsumption | None:
        return await self.update(
            db,
            consumption_id,
            {
                "video_metadata_id": video_metadata_id,
                "status": NewsConsumptionStatus.PRODUCED.value,
            },
        )

    async def mark_published(
        self,
        db: AsyncSession,
        consumption_id: int,
    ) -> ChannelNewsConsumption | None:
        return await self.update(
            db,
            consumption_id,
            {"status": NewsConsumptionStatus.PUBLISHED.value},
        )

    async def release_consumption(
        self,
        db: AsyncSession,
        consumption_id: int,
    ) -> bool:
        """Remove a selected consumption so the news item can be re-claimed."""
        consumption = await self.get_by_id(db, consumption_id)
        if consumption is None or consumption.is_deleted:
            return False
        if consumption.status != NewsConsumptionStatus.SELECTED.value:
            return False
        if consumption.video_metadata_id is not None:
            return False
        return await self.hard_delete(db, consumption_id)


async def release_consumption(db: AsyncSession, consumption_id: int) -> bool:
    return await ChannelNewsConsumptionCrud().release_consumption(db, consumption_id)
