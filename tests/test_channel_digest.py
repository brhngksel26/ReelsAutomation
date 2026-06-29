from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.enums import GenerationStatus, PublishStatus
from src.cruds.channel import ChannelCrud, PlatformConfigCrud
from src.cruds.pipeline_run import PipelineRunCrud
from src.cruds.video import VideoMetadataCrud, VideoPublishStatusCrud
from src.services.channel_digest import build_channel_digest, digest_window_utc
from src.services.platform import validate_platform_specific_settings
from tests.platform_credentials_fixtures import YOUTUBE_CREDENTIALS

CHANNEL_DATA = {
    "name": "Digest Channel",
    "niche": "Entertainment",
    "target_audience": "Fans",
    "language": "en",
    "tone_of_voice": "dramatic",
    "system_prompt": "Celebrity news",
    "daily_video_count": 1,
    "posting_hours": [],
    "base_hashtags": ["celeb"],
}


@pytest.fixture
async def digest_channel(client: AsyncClient, auth_headers: dict) -> int:
    response = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json=CHANNEL_DATA,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_validate_platform_specific_settings_accepts_profile_url():
    validated = validate_platform_specific_settings(
        {"profile_url": " https://youtube.com/@CelebSpill "},
    )
    assert validated["profile_url"] == "https://youtube.com/@CelebSpill"


def test_validate_platform_specific_settings_rejects_invalid_profile_url():
    with pytest.raises(ValueError, match="http"):
        validate_platform_specific_settings({"profile_url": "not-a-url"})


@pytest.mark.asyncio
async def test_build_channel_digest_aggregates_window_stats(
    db_session: AsyncSession,
    digest_channel: int,
):
    now = datetime.now(timezone.utc)
    since, until = digest_window_utc(now)
    published_at = now - timedelta(hours=1)

    channel = await ChannelCrud().get_by_id(db_session, digest_channel)
    assert channel is not None

    await PlatformConfigCrud().create(
        db_session,
        {
            "channel_id": digest_channel,
            "platform_type": "youtube_shorts",
            "credentials_json": YOUTUBE_CREDENTIALS,
            "platform_specific_settings": {
                "profile_url": "https://youtube.com/@DigestChannel",
            },
            "status": "connected",
        },
    )

    video = await VideoMetadataCrud().create(
        db_session,
        {
            "channel_id": digest_channel,
            "hook_text": "Digest hook",
            "caption": "Digest caption",
            "generated_hashtags": ["celeb"],
            "generation_status": GenerationStatus.COMPLETED.value,
            "video_path": "/storage/videos/100.mp4",
            "scheduled_at": published_at,
        },
    )
    await VideoPublishStatusCrud().upsert_for_platform(
        db_session,
        video.id,
        "youtube_shorts",
        PublishStatus.PUBLISHED,
        platform_video_id="digest123",
        published_at=published_at,
    )

    failed_video = await VideoMetadataCrud().create(
        db_session,
        {
            "channel_id": digest_channel,
            "hook_text": "Failed hook",
            "caption": "Failed caption",
            "generated_hashtags": ["celeb"],
            "generation_status": GenerationStatus.COMPLETED.value,
            "video_path": "/storage/videos/101.mp4",
            "scheduled_at": published_at,
        },
    )
    await VideoPublishStatusCrud().upsert_for_platform(
        db_session,
        failed_video.id,
        "youtube_shorts",
        PublishStatus.FAILED,
        error_log="upload limit exceeded",
    )

    run = await PipelineRunCrud().create_run(db_session, digest_channel)
    run_id = str(run.id)
    await PipelineRunCrud().mark_running(db_session, run_id)
    await PipelineRunCrud().mark_failed(db_session, run_id, last_error="idea rejected")

    digest = await build_channel_digest(
        db_session,
        channel,
        since=since,
        until=datetime.now(timezone.utc),
    )

    assert digest.channel_name == "Digest Channel"
    assert len(digest.published) == 1
    assert digest.published[0].platform_url == "https://youtube.com/shorts/digest123"
    assert len(digest.failed_publishes) == 1
    assert digest.failed_publishes[0].video_id == failed_video.id
    assert len(digest.failed_pipelines) == 1
    assert digest.retry_pending_publishes == 1
    assert digest.retry_pending_pipelines == 1
    assert digest.profile_links[0].profile_url == "https://youtube.com/@DigestChannel"
