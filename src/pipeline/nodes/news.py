from __future__ import annotations

import logging

from src.core.config import settings
from src.core.database import pipeline_async_session_maker
from src.core.deps import (
    get_channel_crud,
    get_rss_feed_crud,
    get_rss_news_item_crud,
)
from src.core.unit_of_work import transaction
from src.pipeline.exceptions import PipelineChannelNotFoundError
from src.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def _news_item_to_state(item) -> dict:
    return {
        "id": item.id,
        "feed_id": item.feed_id,
        "title": item.title,
        "summary": item.summary,
        "link": item.link,
        "author": item.author,
        "published_at": item.published_at.isoformat() if item.published_at else None,
    }


async def select_news(state: PipelineState) -> dict:
    channel_id = state["channel_id"]

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            channel = await get_channel_crud().get_by_id(db, channel_id)
            if not channel or channel.is_deleted:
                raise PipelineChannelNotFoundError(channel_id)

            feed_ids = await get_rss_feed_crud().get_channel_feed_ids(db, channel_id)
            if not feed_ids:
                logger.info("select_news channel_id=%s no_rss_feeds", channel_id)
                return {
                    "news_required": False,
                    "selected_news_item": None,
                    "news_consumption_id": None,
                    "current_step": "select_news",
                }

            claimed = await get_rss_news_item_crud().claim_next_news_for_channel(
                db,
                channel_id,
                max_age_days=settings.RSS_NEWS_MAX_AGE_DAYS,
            )
            if not claimed:
                logger.info(
                    "select_news channel_id=%s no_unused_news feed_count=%s",
                    channel_id,
                    len(feed_ids),
                )
                return {
                    "news_required": True,
                    "selected_news_item": None,
                    "news_consumption_id": None,
                    "current_step": "select_news",
                }

            news_item, consumption = claimed

    logger.info(
        "select_news channel_id=%s news_item_id=%s consumption_id=%s",
        channel_id,
        news_item.id,
        consumption.id,
    )
    return {
        "news_required": True,
        "selected_news_item": _news_item_to_state(news_item),
        "news_consumption_id": consumption.id,
        "current_step": "select_news",
    }
