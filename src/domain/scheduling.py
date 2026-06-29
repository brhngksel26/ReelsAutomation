from __future__ import annotations

from src.core.enums import SchedulingMode
from src.models.channel import Channel


def channel_scheduling_mode(channel: Channel) -> str:
    mode = channel.scheduling_mode
    if isinstance(mode, SchedulingMode):
        return mode.value
    return str(mode)


def plan_rss_video_count(channel: Channel, unused_count: int) -> int:
    if unused_count <= 0:
        return 0
    return min(
        unused_count,
        channel.rss_max_videos_per_day,
        channel.daily_video_count,
    )
