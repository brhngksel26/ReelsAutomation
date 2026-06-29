from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import SchedulingMode
from src.cruds.channel import ChannelCrud
from src.cruds.pipeline_run import PipelineRunCrud
from src.cruds.rss import RssFeedCrud, RssNewsItemCrud
from src.domain.scheduling import plan_rss_video_count
from src.models.channel import Channel
from src.services.rss_scheduling import (
    compensate_rss_pipeline_gaps,
    dispatch_rss_pipelines_for_channel,
    enqueue_rss_pipeline_runs,
)
from src.tasks.pipeline import _is_rss_news_channel

CHANNEL_DATA = {
    "name": "RSS Scheduler Channel",
    "niche": "Technology",
    "target_audience": "Developers",
    "language": "en",
    "tone_of_voice": "informative",
    "system_prompt": "Explain tech news",
    "daily_video_count": 10,
    "posting_hours": [],
    "base_hashtags": ["tech"],
    "is_active": True,
    "scheduling_mode": SchedulingMode.RSS_NEWS.value,
    "rss_interval_minutes": 30,
    "rss_max_videos_per_day": 20,
}


@pytest.fixture
async def rss_channel(db_session: AsyncSession, profile_id: int) -> Channel:
    return await ChannelCrud().create(
        db_session,
        {"profile_id": profile_id, **CHANNEL_DATA},
    )


@pytest.fixture
async def profile_id(db_session: AsyncSession) -> int:
    from src.cruds.auth import ProfileCrud, UserCrud

    user = await UserCrud().create(
        db_session,
        {
            "email": f"sched_{datetime.now(timezone.utc).timestamp()}@test.com",
            "hashed_password": "hashed",
            "is_active": True,
            "is_verified": True,
        },
    )
    profile = await ProfileCrud().create(
        db_session, {"user_id": user.id, "tier": "free"}
    )
    return profile.id


def test_plan_video_count_caps_by_limits():
    channel = Channel(
        id=1,
        profile_id=1,
        **CHANNEL_DATA,
    )
    assert plan_rss_video_count(channel, 10) == 10
    assert plan_rss_video_count(channel, 25) == 10
    channel.daily_video_count = 3
    assert plan_rss_video_count(channel, 10) == 3


def test_is_rss_news_channel():
    channel = Channel(id=1, profile_id=1, **CHANNEL_DATA)
    assert _is_rss_news_channel(channel) is True
    channel.scheduling_mode = SchedulingMode.FIXED_HOURS.value
    assert _is_rss_news_channel(channel) is False


@patch("src.tasks.pipeline.run_channel_pipeline_task")
def test_enqueue_rss_pipeline_runs_staggers_countdown(mock_task):
    mock_task.apply_async = MagicMock()
    run_ids = ["run-a", "run-b", "run-c"]
    scheduled = enqueue_rss_pipeline_runs(7, run_ids, 30)
    assert scheduled == 3
    assert mock_task.apply_async.call_count == 3
    countdowns = [
        call.kwargs["countdown"] for call in mock_task.apply_async.call_args_list
    ]
    assert countdowns == [0, 1800, 3600]
    queues = [call.kwargs["queue"] for call in mock_task.apply_async.call_args_list]
    assert queues == ["pipeline", "pipeline", "pipeline"]
    run_id_args = [
        call.kwargs["args"][1] for call in mock_task.apply_async.call_args_list
    ]
    assert run_id_args == run_ids


@pytest.mark.asyncio
async def test_dispatch_skips_without_feeds(
    db_session: AsyncSession, rss_channel: Channel
):
    scheduled = await dispatch_rss_pipelines_for_channel(db_session, rss_channel)
    assert scheduled == 0


@pytest.mark.asyncio
async def test_dispatch_schedules_unused_news(
    db_session: AsyncSession,
    rss_channel: Channel,
):
    feed = await RssFeedCrud().create(
        db_session,
        {
            "name": "Scheduler Feed",
            "url": f"https://sched.example.com/{datetime.now(timezone.utc).timestamp()}.xml",
            "category": "tech",
            "is_active": True,
        },
    )
    await RssFeedCrud().grant_feeds_to_channel(db_session, rss_channel.id, [feed.id])

    for index in range(3):
        await RssNewsItemCrud().create(
            db_session,
            {
                "feed_id": feed.id,
                "guid": f"guid-{index}",
                "title": f"Story {index}",
                "summary": "Summary",
                "link": f"https://example.com/{index}",
                "author": "Author",
                "published_at": datetime.now(timezone.utc),
                "fetched_at": datetime.now(timezone.utc),
            },
        )

    with patch(
        "src.services.rss_scheduling._create_and_enqueue_runs",
        return_value=3,
    ) as mock_enqueue:
        scheduled = await dispatch_rss_pipelines_for_channel(db_session, rss_channel)

    assert scheduled == 3
    mock_enqueue.assert_called_once()
    assert mock_enqueue.call_args.args[1].id == rss_channel.id
    assert mock_enqueue.call_args.args[2] == 3

    refreshed = await ChannelCrud().get_by_id(db_session, rss_channel.id)
    assert refreshed is not None
    assert refreshed.rss_last_scheduled_date == datetime.now(timezone.utc).date()


@pytest.mark.asyncio
async def test_dispatch_skips_if_already_scheduled_today(
    db_session: AsyncSession,
    rss_channel: Channel,
):
    today = datetime.now(timezone.utc).date()
    await ChannelCrud().update(
        db_session,
        rss_channel.id,
        {"rss_last_scheduled_date": today},
    )
    channel = await ChannelCrud().get_by_id(db_session, rss_channel.id)
    assert channel is not None

    with patch("src.services.rss_scheduling._create_and_enqueue_runs") as mock_enqueue:
        scheduled = await dispatch_rss_pipelines_for_channel(db_session, channel)

    assert scheduled == 0
    mock_enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_compensation_enqueues_gap_runs(
    db_session: AsyncSession,
    rss_channel: Channel,
):
    feed = await RssFeedCrud().create(
        db_session,
        {
            "name": "Compensation Feed",
            "url": f"https://comp.example.com/{datetime.now(timezone.utc).timestamp()}.xml",
            "category": "tech",
            "is_active": True,
        },
    )
    await RssFeedCrud().grant_feeds_to_channel(db_session, rss_channel.id, [feed.id])

    for index in range(5):
        await RssNewsItemCrud().create(
            db_session,
            {
                "feed_id": feed.id,
                "guid": f"comp-guid-{index}",
                "title": f"Story {index}",
                "summary": "Summary",
                "link": f"https://example.com/comp/{index}",
                "author": "Author",
                "published_at": datetime.now(timezone.utc),
                "fetched_at": datetime.now(timezone.utc),
            },
        )

    crud = PipelineRunCrud()
    for _ in range(3):
        run = await crud.create_run(db_session, rss_channel.id)
        await crud.mark_running(db_session, str(run.id))
    completed = await crud.create_run(db_session, rss_channel.id)
    await crud.mark_running(db_session, str(completed.id))
    await crud.mark_completed(db_session, str(completed.id))

    with patch(
        "src.services.rss_scheduling._create_and_enqueue_runs",
        return_value=3,
    ) as mock_enqueue:
        compensated = await compensate_rss_pipeline_gaps(db_session, rss_channel)

    assert compensated == 3
    mock_enqueue.assert_called_once()
    assert mock_enqueue.call_args.args[2] == 3


@pytest.mark.asyncio
async def test_compensation_skips_when_already_scheduled_today_guard_unaffected(
    db_session: AsyncSession,
    rss_channel: Channel,
):
    today = datetime.now(timezone.utc).date()
    await ChannelCrud().update(
        db_session,
        rss_channel.id,
        {"rss_last_scheduled_date": today},
    )
    channel = await ChannelCrud().get_by_id(db_session, rss_channel.id)
    assert channel is not None

    with patch(
        "src.services.rss_scheduling._create_and_enqueue_runs", return_value=0
    ) as mock_enqueue:
        scheduled = await dispatch_rss_pipelines_for_channel(db_session, channel)
        compensated = await compensate_rss_pipeline_gaps(db_session, channel)

    assert scheduled == 0
    assert compensated == 0
    mock_enqueue.assert_not_called()
