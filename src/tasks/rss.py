from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.async_run import run_async
from src.core.celery_app import celery_app
from src.core.config import settings
from src.core.database import worker_async_session_maker
from src.core.deps import get_rss_feed_crud, get_rss_news_item_crud
from src.core.unit_of_work import transaction
from src.integrations.rss_scrapping import fetch_feed
from src.models.rss import RssFeed
from src.services.rss_scheduling import (
    compensate_rss_pipelines_for_all_channels,
    dispatch_rss_pipelines_for_all_channels,
)

logger = logging.getLogger(__name__)


async def _record_feed_scrape_status(
    db: AsyncSession,
    feed: RssFeed,
    *,
    scraped_at: datetime,
    error: str | None,
    item_count: int,
) -> None:
    feed.last_scrape_at = scraped_at
    feed.last_scrape_error = error
    feed.last_item_count = item_count
    await db.flush()


async def _scrape_rss_feeds() -> None:
    if not settings.RSS_ENABLED:
        logger.info("RSS scraping disabled (RSS_ENABLED=false)")
        return

    async with worker_async_session_maker() as db:
        async with transaction(db):
            feeds = await get_rss_feed_crud().list_active(db)
            if not feeds:
                logger.info("No active RSS feeds to scrape")
                return

            news_crud = get_rss_news_item_crud()
            scraped_at = datetime.now(timezone.utc)
            total_new = 0
            ok_count = 0
            failed_count = 0

            for feed in feeds:
                result = await fetch_feed(feed.url)
                if result.error:
                    failed_count += 1
                    logger.warning(
                        "RSS scrape failed feed_id=%s url=%s error=%s",
                        feed.id,
                        feed.url,
                        result.error,
                    )
                    await _record_feed_scrape_status(
                        db,
                        feed,
                        scraped_at=scraped_at,
                        error=result.error,
                        item_count=0,
                    )
                    continue

                for item in result.items:
                    created = await news_crud.upsert_item(
                        db,
                        feed.id,
                        item,
                        fetched_at=scraped_at,
                    )
                    if created:
                        total_new += 1

                ok_count += 1
                await _record_feed_scrape_status(
                    db,
                    feed,
                    scraped_at=scraped_at,
                    error=None,
                    item_count=len(result.items),
                )

            logger.info(
                "RSS scrape complete feeds=%s ok=%s failed=%s new_items=%s",
                len(feeds),
                ok_count,
                failed_count,
                total_new,
            )

    async with worker_async_session_maker() as db:
        async with transaction(db):
            scheduled = await dispatch_rss_pipelines_for_all_channels(db)
            if scheduled:
                logger.info("RSS pipeline dispatch scheduled channels=%s", scheduled)

            compensated = await compensate_rss_pipelines_for_all_channels(db)
            if compensated:
                logger.info(
                    "RSS pipeline compensation scheduled channels=%s", compensated
                )


@celery_app.task(name="src.tasks.rss.scrape_rss_feeds")
def scrape_rss_feeds() -> None:
    run_async(_scrape_rss_feeds())
