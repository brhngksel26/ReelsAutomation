from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.deps import (
    get_channel_crud,
    get_pipeline_run_crud,
    get_rss_feed_crud,
    get_rss_news_item_crud,
)
from src.core.enums import SchedulingMode
from src.domain.scheduling import channel_scheduling_mode, plan_rss_video_count
from src.models.channel import Channel
from src.protocols.channel import ChannelRepository
from src.protocols.pipeline import PipelineRunRepository
from src.protocols.rss import RssFeedRepository, RssNewsItemRepository

logger = logging.getLogger(__name__)


def enqueue_rss_pipeline_runs(
    channel_id: int,
    run_ids: list[str],
    interval_minutes: int,
) -> int:
    """Schedule pipeline Celery tasks with staggered countdowns."""
    from src.tasks.pipeline import run_channel_pipeline_task

    video_count = len(run_ids)
    if video_count <= 0:
        return 0

    for index, run_id in enumerate(run_ids):
        countdown_seconds = index * interval_minutes * 60
        run_channel_pipeline_task.apply_async(
            args=[channel_id, run_id],
            countdown=countdown_seconds,
            queue="pipeline",
        )
        logger.info(
            "Scheduled RSS pipeline channel_id=%s run=%s/%s run_id=%s countdown_seconds=%s",
            channel_id,
            index + 1,
            video_count,
            run_id,
            countdown_seconds,
        )
    return video_count


async def _create_and_enqueue_runs(
    db: AsyncSession,
    channel: Channel,
    video_count: int,
    *,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> int:
    pipeline_run_crud = pipeline_run_crud or get_pipeline_run_crud()
    run_ids = await pipeline_run_crud.create_pending_runs(db, channel.id, video_count)
    interval_minutes = channel.rss_interval_minutes
    return enqueue_rss_pipeline_runs(channel.id, run_ids, interval_minutes)


async def compensate_rss_pipeline_gaps(
    db: AsyncSession,
    channel: Channel,
    *,
    feed_crud: RssFeedRepository | None = None,
    news_item_crud: RssNewsItemRepository | None = None,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> int:
    """Enqueue telafi pipelines when scheduled runs exceed completed runs today."""
    feed_crud = feed_crud or get_rss_feed_crud()
    news_item_crud = news_item_crud or get_rss_news_item_crud()
    pipeline_run_crud = pipeline_run_crud or get_pipeline_run_crud()

    if channel_scheduling_mode(channel) != SchedulingMode.RSS_NEWS.value:
        return 0
    if not channel.is_active or channel.is_deleted:
        return 0

    feed_ids = await feed_crud.get_channel_feed_ids(db, channel.id)
    if not feed_ids:
        return 0

    scheduled_today = await pipeline_run_crud.count_scheduled_today(db, channel.id)
    completed_today = await pipeline_run_crud.count_completed_today(db, channel.id)
    gap = scheduled_today - completed_today
    if gap <= 0:
        return 0

    unused_count = await news_item_crud.count_unused_for_channel(
        db,
        channel.id,
        max_age_days=settings.RSS_NEWS_MAX_AGE_DAYS,
    )
    remaining_daily_slots = max(channel.rss_max_videos_per_day - completed_today, 0)
    telafi_count = min(gap, unused_count, remaining_daily_slots)
    if telafi_count <= 0:
        logger.info(
            "RSS compensation skipped channel_id=%s gap=%s unused=%s remaining_slots=%s",
            channel.id,
            gap,
            unused_count,
            remaining_daily_slots,
        )
        return 0

    scheduled = await _create_and_enqueue_runs(
        db,
        channel,
        telafi_count,
        pipeline_run_crud=pipeline_run_crud,
    )
    logger.info(
        "RSS compensation channel_id=%s gap=%s telafi=%s scheduled_today=%s completed_today=%s",
        channel.id,
        gap,
        scheduled,
        scheduled_today,
        completed_today,
    )
    return scheduled


async def dispatch_rss_pipelines_for_channel(
    db: AsyncSession,
    channel: Channel,
    *,
    force: bool = False,
    feed_crud: RssFeedRepository | None = None,
    news_item_crud: RssNewsItemRepository | None = None,
    channel_crud: ChannelRepository | None = None,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> int:
    feed_crud = feed_crud or get_rss_feed_crud()
    news_item_crud = news_item_crud or get_rss_news_item_crud()
    channel_crud = channel_crud or get_channel_crud()
    pipeline_run_crud = pipeline_run_crud or get_pipeline_run_crud()

    if channel_scheduling_mode(channel) != SchedulingMode.RSS_NEWS.value:
        return 0
    if not channel.is_active or channel.is_deleted:
        return 0

    feed_ids = await feed_crud.get_channel_feed_ids(db, channel.id)
    if not feed_ids:
        return 0

    today = datetime.now(timezone.utc).date()
    if not force and channel.rss_last_scheduled_date == today:
        logger.info(
            "Skipping RSS dispatch for channel_id=%s; already scheduled today",
            channel.id,
        )
        return 0

    unused_count = await news_item_crud.count_unused_for_channel(
        db,
        channel.id,
        max_age_days=settings.RSS_NEWS_MAX_AGE_DAYS,
    )
    if unused_count < channel.daily_video_count:
        logger.warning(
            "Low RSS news stock channel_id=%s unused_count=%s daily_video_count=%s",
            channel.id,
            unused_count,
            channel.daily_video_count,
        )
    video_count = plan_rss_video_count(channel, unused_count)
    if video_count <= 0:
        logger.info(
            "No RSS videos to schedule channel_id=%s unused_count=%s",
            channel.id,
            unused_count,
        )
        return 0

    scheduled = await _create_and_enqueue_runs(
        db,
        channel,
        video_count,
        pipeline_run_crud=pipeline_run_crud,
    )

    await channel_crud.update(
        db,
        channel.id,
        {"rss_last_scheduled_date": today},
    )
    logger.info(
        "RSS dispatch channel_id=%s videos=%s interval_minutes=%s",
        channel.id,
        scheduled,
        channel.rss_interval_minutes,
    )
    return scheduled


async def dispatch_rss_pipelines_for_all_channels(
    db: AsyncSession,
    *,
    force: bool = False,
    feed_crud: RssFeedRepository | None = None,
    news_item_crud: RssNewsItemRepository | None = None,
    channel_crud: ChannelRepository | None = None,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> dict[int, int]:
    feed_crud = feed_crud or get_rss_feed_crud()

    channels = await feed_crud.list_rss_news_channels(db)

    scheduled_by_channel: dict[int, int] = {}
    for channel in channels:
        count = await dispatch_rss_pipelines_for_channel(
            db,
            channel,
            force=force,
            feed_crud=feed_crud,
            news_item_crud=news_item_crud,
            channel_crud=channel_crud,
            pipeline_run_crud=pipeline_run_crud,
        )
        if count > 0:
            scheduled_by_channel[channel.id] = count
    return scheduled_by_channel


async def compensate_rss_pipelines_for_all_channels(
    db: AsyncSession,
    *,
    feed_crud: RssFeedRepository | None = None,
    news_item_crud: RssNewsItemRepository | None = None,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> dict[int, int]:
    feed_crud = feed_crud or get_rss_feed_crud()

    channels = await feed_crud.list_rss_news_channels(db)

    compensated_by_channel: dict[int, int] = {}
    for channel in channels:
        count = await compensate_rss_pipeline_gaps(
            db,
            channel,
            feed_crud=feed_crud,
            news_item_crud=news_item_crud,
            pipeline_run_crud=pipeline_run_crud,
        )
        if count > 0:
            compensated_by_channel[channel.id] = count
    return compensated_by_channel
