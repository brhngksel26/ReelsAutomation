from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import (
    get_channel_crud,
    get_pipeline_run_crud,
    get_platform_config_crud,
    get_video_publish_status_crud,
)
from src.integrations.ntfy import _build_platform_url, _platform_label
from src.models.channel import Channel
from src.protocols.channel import ChannelRepository, PlatformConfigRepository
from src.protocols.pipeline import PipelineRunRepository
from src.protocols.video import VideoPublishStatusRepository
from src.schemas.channel_digest import (
    ChannelDigestOut,
    ChannelProfileLink,
    FailedPipelineDigestItem,
    FailedPublishDigestItem,
    PublishedVideoDigestItem,
)


def digest_window_utc(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, current


def _extract_profile_links(platform_configs) -> list[ChannelProfileLink]:
    links: list[ChannelProfileLink] = []
    for config in platform_configs:
        settings = config.platform_specific_settings or {}
        raw_url = settings.get("profile_url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        platform_type = str(config.platform_type)
        links.append(
            ChannelProfileLink(
                platform_type=platform_type,
                platform_label=_platform_label(platform_type),
                profile_url=raw_url.strip(),
            )
        )
    return links


async def build_channel_digest(
    db: AsyncSession,
    channel: Channel,
    *,
    since: datetime,
    until: datetime,
    publish_crud: VideoPublishStatusRepository | None = None,
    pipeline_crud: PipelineRunRepository | None = None,
    platform_config_crud: PlatformConfigRepository | None = None,
) -> ChannelDigestOut:
    publish_crud = publish_crud or get_video_publish_status_crud()
    pipeline_crud = pipeline_crud or get_pipeline_run_crud()
    platform_config_crud = platform_config_crud or get_platform_config_crud()

    platform_configs = await platform_config_crud.get_by_channel_id(db, channel.id)

    published_rows = await publish_crud.list_published_in_window(
        db,
        channel.id,
        since=since,
        until=until,
    )
    failed_publish_rows = await publish_crud.list_failed_in_window(
        db,
        channel.id,
        since=since,
        until=until,
    )
    failed_pipeline_runs = await pipeline_crud.list_failed_in_window(
        db,
        channel.id,
        since=since,
        until=until,
    )
    retry_pending_publishes = await publish_crud.list_failed_for_channel(db, channel.id)
    retry_pending_pipelines = await pipeline_crud.list_retryable_for_channel(
        db, channel.id
    )

    published = [
        PublishedVideoDigestItem(
            video_id=video.id,
            hook_text=video.hook_text,
            platform_type=str(status.platform_type),
            platform_label=_platform_label(str(status.platform_type)),
            platform_url=(
                _build_platform_url(str(status.platform_type), status.platform_video_id)
                if status.platform_video_id
                else None
            ),
        )
        for video, status in published_rows
    ]
    failed_publishes = [
        FailedPublishDigestItem(
            video_id=video.id,
            hook_text=video.hook_text,
            platform_type=str(status.platform_type),
            platform_label=_platform_label(str(status.platform_type)),
            error_log=status.error_log,
        )
        for video, status in failed_publish_rows
    ]
    failed_pipelines = [
        FailedPipelineDigestItem(
            run_id=str(run.id),
            last_error=run.last_error,
            current_step=run.current_step,
        )
        for run in failed_pipeline_runs
    ]

    return ChannelDigestOut(
        channel_id=channel.id,
        channel_name=channel.name,
        digest_date=until.date(),
        published=published,
        failed_publishes=failed_publishes,
        failed_pipelines=failed_pipelines,
        retry_pending_publishes=len(retry_pending_publishes),
        retry_pending_pipelines=len(retry_pending_pipelines),
        profile_links=_extract_profile_links(platform_configs),
    )


async def build_daily_digests_for_active_channels(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    channel_crud: ChannelRepository | None = None,
    publish_crud: VideoPublishStatusRepository | None = None,
    pipeline_crud: PipelineRunRepository | None = None,
    platform_config_crud: PlatformConfigRepository | None = None,
) -> list[ChannelDigestOut]:
    channel_crud = channel_crud or get_channel_crud()

    since, until = digest_window_utc(now)
    channels = await channel_crud.list_active(db)
    digests: list[ChannelDigestOut] = []
    for channel in channels:
        digests.append(
            await build_channel_digest(
                db,
                channel,
                since=since,
                until=until,
                publish_crud=publish_crud,
                pipeline_crud=pipeline_crud,
                platform_config_crud=platform_config_crud,
            )
        )
    return digests
