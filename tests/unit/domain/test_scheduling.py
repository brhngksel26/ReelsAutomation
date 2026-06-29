from __future__ import annotations

import pytest

from src.core.enums import SchedulingMode
from src.domain.scheduling import channel_scheduling_mode, plan_rss_video_count
from src.models.channel import Channel

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


def _channel(**overrides) -> Channel:
    return Channel(id=1, profile_id=1, **{**CHANNEL_DATA, **overrides})


def test_channel_scheduling_mode_returns_enum_value():
    channel = _channel(scheduling_mode=SchedulingMode.RSS_NEWS)
    assert channel_scheduling_mode(channel) == SchedulingMode.RSS_NEWS.value


def test_channel_scheduling_mode_returns_string_when_not_enum():
    channel = _channel(scheduling_mode=SchedulingMode.FIXED_HOURS.value)
    assert channel_scheduling_mode(channel) == SchedulingMode.FIXED_HOURS.value


@pytest.mark.parametrize(
    ("unused_count", "daily_video_count", "rss_max", "expected"),
    [
        (0, 10, 20, 0),
        (-1, 10, 20, 0),
        (10, 10, 20, 10),
        (25, 10, 20, 10),
        (10, 3, 20, 3),
        (10, 10, 5, 5),
        (100, 10, 5, 5),
    ],
)
def test_plan_rss_video_count_caps_by_limits(
    unused_count: int,
    daily_video_count: int,
    rss_max: int,
    expected: int,
):
    channel = _channel(
        daily_video_count=daily_video_count,
        rss_max_videos_per_day=rss_max,
    )
    assert plan_rss_video_count(channel, unused_count) == expected
