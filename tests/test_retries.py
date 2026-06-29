from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.enums import GenerationStatus, PipelineRunStatus, PublishStatus
from src.cruds.auth import ProfileCrud, UserCrud
from src.cruds.channel import ChannelCrud
from src.cruds.pipeline_run import PipelineRunCrud
from src.cruds.video import VideoMetadataCrud, VideoPublishStatusCrud

CHANNEL_DATA = {
    "name": "Retry Channel",
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
async def owned_channel_id(client: AsyncClient, auth_headers: dict) -> int:
    response = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json=CHANNEL_DATA,
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
async def failed_pipeline_run(
    db_session: AsyncSession,
    owned_channel_id: int,
) -> str:
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, owned_channel_id)
    run_id = str(run.id)
    await crud.mark_running(db_session, run_id)
    await crud.mark_failed(db_session, run_id, last_error="idea rejected")
    await db_session.commit()
    return run_id


@pytest.fixture
async def failed_publish_video(
    db_session: AsyncSession,
    owned_channel_id: int,
) -> int:
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=1)
    video = await VideoMetadataCrud().create(
        db_session,
        {
            "channel_id": owned_channel_id,
            "hook_text": "Retry hook",
            "caption": "Retry caption",
            "generated_hashtags": ["celeb"],
            "generation_status": GenerationStatus.COMPLETED.value,
            "video_path": "/storage/videos/99.mp4",
            "scheduled_at": scheduled_at,
        },
    )
    await VideoPublishStatusCrud().upsert_for_platform(
        db_session,
        video.id,
        "youtube_shorts",
        PublishStatus.FAILED,
        error_log="upload limit exceeded",
    )
    await db_session.commit()
    return video.id


@pytest.mark.asyncio
async def test_list_retryable_pipelines(
    client: AsyncClient,
    auth_headers: dict,
    failed_pipeline_run: str,
):
    response = await client.get("/api/v1/retries/pipelines", headers=auth_headers)
    assert response.status_code == 200
    run_ids = [item["id"] for item in response.json()]
    assert failed_pipeline_run in run_ids


@pytest.mark.asyncio
async def test_list_failed_publishes(
    client: AsyncClient,
    auth_headers: dict,
    failed_publish_video: int,
):
    response = await client.get("/api/v1/retries/publishes", headers=auth_headers)
    assert response.status_code == 200
    video_ids = [item["video_id"] for item in response.json()]
    assert failed_publish_video in video_ids


@pytest.mark.asyncio
async def test_retry_pipeline_run_enqueues_task(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    failed_pipeline_run: str,
):
    mock_result = MagicMock()
    mock_result.id = "pipeline-task-1"
    with patch(
        "src.tasks.pipeline.run_channel_pipeline_task.apply_async",
        return_value=mock_result,
    ) as mock_apply:
        response = await client.post(
            f"/api/v1/retries/pipelines/{failed_pipeline_run}",
            headers=auth_headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["enqueued"] == 1
    assert body["run_ids"] == [failed_pipeline_run]
    mock_apply.assert_called_once()

    run = await PipelineRunCrud().get_by_id(db_session, failed_pipeline_run)
    assert run is not None
    assert run.status == PipelineRunStatus.PENDING.value
    assert run.retry_count == 1


@pytest.mark.asyncio
async def test_retry_exhausted_pipeline_returns_409(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    owned_channel_id: int,
):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, owned_channel_id)
    run_id = str(run.id)
    await crud.mark_running(db_session, run_id)
    await crud.mark_failed(db_session, run_id, last_error="failed")
    loaded = await crud.get_by_id(db_session, run_id)
    assert loaded is not None
    loaded.retry_count = settings.PIPELINE_MAX_RETRIES
    await db_session.commit()

    response = await client.post(
        f"/api/v1/retries/pipelines/{run_id}",
        headers=auth_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_retry_pipeline_run_not_owned_returns_404(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    other_user = await UserCrud().create(
        db_session,
        {
            "email": f"other_{uuid4()}@test.com",
            "hashed_password": "hashed",
            "is_active": True,
            "is_verified": True,
        },
    )
    other_profile = await ProfileCrud().create(
        db_session,
        {"user_id": other_user.id, "tier": "free"},
    )
    other_channel = await ChannelCrud().create(
        db_session,
        {
            "profile_id": other_profile.id,
            "name": "Other Channel",
            "niche": "Sports",
            "target_audience": "Fans",
            "language": "en",
            "tone_of_voice": "casual",
            "system_prompt": "Sports news",
            "daily_video_count": 1,
            "posting_hours": [],
            "base_hashtags": ["sports"],
            "is_active": True,
        },
    )
    run = await PipelineRunCrud().create_run(db_session, other_channel.id)
    run_id = str(run.id)
    await PipelineRunCrud().mark_running(db_session, run_id)
    await PipelineRunCrud().mark_failed(db_session, run_id, last_error="x")

    response = await client.post(
        f"/api/v1/retries/pipelines/{run_id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_publish_enqueues_task(
    client: AsyncClient,
    auth_headers: dict,
    failed_publish_video: int,
):
    with patch(
        "src.tasks.video.publish_to_platforms_task.delay",
        return_value=MagicMock(id="publish-task-1"),
    ) as mock_delay:
        response = await client.post(
            f"/api/v1/retries/publishes/{failed_publish_video}",
            headers=auth_headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["enqueued"] == 1
    assert body["video_ids"] == [failed_publish_video]
    mock_delay.assert_called_once_with(failed_publish_video)


@pytest.mark.asyncio
async def test_retry_all_pipelines(
    client: AsyncClient,
    auth_headers: dict,
    failed_pipeline_run: str,
):
    mock_result = MagicMock()
    mock_result.id = "pipeline-task-all"
    with patch(
        "src.tasks.pipeline.run_channel_pipeline_task.apply_async",
        return_value=mock_result,
    ):
        response = await client.post(
            "/api/v1/retries/pipelines/retry-all",
            headers=auth_headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["enqueued"] >= 1
    assert failed_pipeline_run in body["run_ids"]


@pytest.mark.asyncio
async def test_retry_all_publishes(
    client: AsyncClient,
    auth_headers: dict,
    failed_publish_video: int,
):
    with patch(
        "src.tasks.video.publish_to_platforms_task.delay",
        return_value=MagicMock(id="publish-task-all"),
    ):
        response = await client.post(
            "/api/v1/retries/publishes/retry-all",
            headers=auth_headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["enqueued"] >= 1
    assert failed_publish_video in body["video_ids"]
