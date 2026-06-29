from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_exception import CrudIntegrityError
from src.core.deps import get_rss_feed_crud, get_rss_news_item_crud
from src.models.auth import User
from src.models.rss import RssFeed
from src.protocols.channel import ChannelRepository
from src.protocols.pipeline import PipelineRunRepository
from src.protocols.rss import RssFeedRepository, RssNewsItemRepository
from src.schemas.rss import RssFeedCreateIn
from src.services.ownership import get_owned_channel
from src.services.rss_scheduling import dispatch_rss_pipelines_for_channel
from src.tasks.rss import scrape_rss_feeds


async def list_feeds(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
    feed_crud: RssFeedRepository | None = None,
) -> list[RssFeed]:
    feed_crud = feed_crud or get_rss_feed_crud()
    return await feed_crud.get_many(
        db,
        skip=skip,
        limit=limit,
        is_deleted=False,
    )


async def create_feed(
    db: AsyncSession,
    data: RssFeedCreateIn,
    *,
    feed_crud: RssFeedRepository | None = None,
) -> RssFeed:
    feed_crud = feed_crud or get_rss_feed_crud()
    try:
        return await feed_crud.create(db, data.model_dump())
    except CrudIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def grant_feeds_to_channel(
    db: AsyncSession,
    user: User,
    channel_id: int,
    feed_ids: list[int],
    *,
    feed_crud: RssFeedRepository | None = None,
) -> list[RssFeed]:
    feed_crud = feed_crud or get_rss_feed_crud()
    channel = await get_owned_channel(db, user, channel_id)
    for feed_id in feed_ids:
        feed = await feed_crud.get_by_id(db, feed_id)
        if not feed or feed.is_deleted:
            raise HTTPException(status_code=404, detail=f"Feed {feed_id} not found")
    await feed_crud.grant_feeds_to_channel(db, channel.id, feed_ids)
    return await list_channel_granted_feeds(
        db,
        user,
        channel_id,
        feed_crud=feed_crud,
    )


async def revoke_feed_from_channel(
    db: AsyncSession,
    user: User,
    channel_id: int,
    feed_id: int,
    *,
    feed_crud: RssFeedRepository | None = None,
) -> None:
    feed_crud = feed_crud or get_rss_feed_crud()
    await get_owned_channel(db, user, channel_id)
    revoked = await feed_crud.revoke_feed_from_channel(db, channel_id, feed_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Feed grant not found for channel")


async def list_channel_news(
    db: AsyncSession,
    user: User,
    channel_id: int,
    *,
    skip: int = 0,
    limit: int = 50,
    news_item_crud: RssNewsItemRepository | None = None,
):
    news_item_crud = news_item_crud or get_rss_news_item_crud()
    await get_owned_channel(db, user, channel_id)
    return await news_item_crud.list_for_channel(
        db,
        channel_id,
        skip=skip,
        limit=limit,
    )


async def list_channel_granted_feeds(
    db: AsyncSession,
    user: User,
    channel_id: int,
    *,
    feed_crud: RssFeedRepository | None = None,
) -> list[RssFeed]:
    feed_crud = feed_crud or get_rss_feed_crud()
    channel = await get_owned_channel(db, user, channel_id)
    feed_ids = await feed_crud.get_channel_feed_ids(db, channel.id)
    if not feed_ids:
        return []
    result = await db.execute(
        select(RssFeed).where(
            RssFeed.id.in_(feed_ids),
            RssFeed.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


def trigger_rss_scrape() -> str:
    task = scrape_rss_feeds.delay()
    return task.id


async def schedule_channel_pipelines(
    db: AsyncSession,
    user: User,
    channel_id: int,
    *,
    force: bool = False,
    feed_crud: RssFeedRepository | None = None,
    news_item_crud: RssNewsItemRepository | None = None,
    channel_crud: ChannelRepository | None = None,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> dict:
    channel = await get_owned_channel(db, user, channel_id)
    scheduled = await dispatch_rss_pipelines_for_channel(
        db,
        channel,
        force=force,
        feed_crud=feed_crud,
        news_item_crud=news_item_crud,
        channel_crud=channel_crud,
        pipeline_run_crud=pipeline_run_crud,
    )
    return {
        "channel_id": channel.id,
        "scheduled_videos": scheduled,
        "interval_minutes": channel.rss_interval_minutes,
    }
