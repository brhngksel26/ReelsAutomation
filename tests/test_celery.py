from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.core.enums import GenerationStatus, PublishStatus
from src.cruds.video import VideoMetadataCrud, VideoPublishStatusCrud
from src.tasks.video import check_due_videos, publish_to_platforms_task
from tests.platform_credentials_fixtures import (
    INSTAGRAM_CREDENTIALS,
    YOUTUBE_CREDENTIALS,
)


@pytest.mark.asyncio
async def test_celery_generation_and_publish(
    client: AsyncClient, auth_headers: dict, db_session
):
    channel = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Celery Channel",
            "niche": "Tech",
            "target_audience": "All",
            "language": "en",
            "tone_of_voice": "casual",
        },
    )
    channel_id = channel.json()["id"]

    await client.post(
        "/api/v1/platforms/connect",
        headers=auth_headers,
        json={
            "channel_id": channel_id,
            "platform_type": "instagram",
            "credentials_json": INSTAGRAM_CREDENTIALS,
        },
    )

    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    video_resp = await client.post(
        "/api/v1/videos/schedule",
        headers=auth_headers,
        json={
            "channel_id": channel_id,
            "hook_text": "Celery hook",
            "caption": "Celery caption",
            "scheduled_at": past,
        },
    )
    assert video_resp.status_code == 201
    video_id = video_resp.json()["id"]

    video = await VideoMetadataCrud().get_by_id(db_session, video_id)
    assert video.generation_status == GenerationStatus.COMPLETED.value
    assert video.video_path is not None

    mock_upload = AsyncMock(return_value="ig-media-celery-123")
    with patch(
        "src.services.uploaders.instagram.InstagramUploader.upload",
        mock_upload,
    ):
        publish_to_platforms_task(video_id)

    statuses = await VideoPublishStatusCrud().get_by_video_id(db_session, video_id)
    assert len(statuses) == 1
    assert statuses[0].publish_status == PublishStatus.PUBLISHED.value
    assert statuses[0].platform_video_id == "ig-media-celery-123"
    mock_upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_check_due_videos_enqueues_publish(
    client: AsyncClient, auth_headers: dict, db_session
):
    channel = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Beat Channel",
            "niche": "News",
            "target_audience": "All",
            "language": "en",
            "tone_of_voice": "formal",
        },
    )
    channel_id = channel.json()["id"]

    await client.post(
        "/api/v1/platforms/connect",
        headers=auth_headers,
        json={
            "channel_id": channel_id,
            "platform_type": "youtube_shorts",
            "credentials_json": YOUTUBE_CREDENTIALS,
        },
    )

    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    video_resp = await client.post(
        "/api/v1/videos/schedule",
        headers=auth_headers,
        json={
            "channel_id": channel_id,
            "hook_text": "Beat hook",
            "caption": "Beat caption",
            "scheduled_at": past,
        },
    )
    video_id = video_resp.json()["id"]

    mock_upload = AsyncMock(return_value="yt-celery-456")
    with patch(
        "src.services.uploaders.youtube.YouTubeShortsUploader.upload",
        mock_upload,
    ):
        check_due_videos()

    statuses = await VideoPublishStatusCrud().get_by_video_id(db_session, video_id)
    assert any(s.publish_status == PublishStatus.PUBLISHED.value for s in statuses)
    assert any(s.platform_video_id == "yt-celery-456" for s in statuses)
