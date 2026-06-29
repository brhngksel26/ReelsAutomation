from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.enums import PipelineRunStatus
from src.cruds.pipeline_run import PipelineRunCrud
from src.models.channel import Channel

CHANNEL_DATA = {
    "name": "Pipeline Run Channel",
    "niche": "Technology",
    "target_audience": "Developers",
    "language": "en",
    "tone_of_voice": "informative",
    "system_prompt": "Explain tech news",
    "daily_video_count": 1,
    "posting_hours": [],
    "base_hashtags": ["tech"],
    "is_active": True,
}


@pytest.fixture
async def channel(db_session: AsyncSession, profile_id: int) -> Channel:
    from src.cruds.channel import ChannelCrud

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
            "email": f"run_{datetime.now(timezone.utc).timestamp()}@test.com",
            "hashed_password": "hashed",
            "is_active": True,
            "is_verified": True,
        },
    )
    profile = await ProfileCrud().create(
        db_session, {"user_id": user.id, "tier": "free"}
    )
    return profile.id


@pytest.mark.asyncio
async def test_create_run_sets_pending_status(
    db_session: AsyncSession, channel: Channel
):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, channel.id)

    assert run.status == PipelineRunStatus.PENDING.value
    assert run.channel_id == channel.id
    assert run.thread_id == f"channel-{channel.id}-{run.id}"
    assert run.retry_count == 0


@pytest.mark.asyncio
async def test_mark_running_and_completed(db_session: AsyncSession, channel: Channel):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, channel.id)
    run_id = str(run.id)

    running = await crud.mark_running(db_session, run_id, celery_task_id="celery-123")
    assert running is not None
    assert running.status == PipelineRunStatus.RUNNING.value
    assert running.celery_task_id == "celery-123"
    assert running.started_at is not None

    completed = await crud.mark_completed(
        db_session,
        run_id,
        current_step="published",
    )
    assert completed is not None
    assert completed.status == PipelineRunStatus.COMPLETED.value
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_mark_failed_and_increment_retry(
    db_session: AsyncSession, channel: Channel
):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, channel.id)
    run_id = str(run.id)

    await crud.mark_running(db_session, run_id)
    failed = await crud.mark_failed(db_session, run_id, last_error="boom")
    assert failed is not None
    assert failed.status == PipelineRunStatus.FAILED.value
    assert failed.last_error == "boom"

    updated = await crud.increment_retry_count(db_session, run_id)
    assert updated is not None
    assert updated.retry_count == 1


@pytest.mark.asyncio
async def test_list_stale_running(db_session: AsyncSession, channel: Channel):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, channel.id)
    run_id = str(run.id)
    await crud.mark_running(db_session, run_id)

    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=settings.PIPELINE_STALE_AFTER_MINUTES + 1
    )
    loaded = await crud.get_by_id(db_session, run_id)
    assert loaded is not None
    loaded.updated_at = stale_cutoff
    await db_session.commit()

    stale_runs = await crud.list_stale_running(db_session)
    assert any(str(item.id) == run_id for item in stale_runs)


@pytest.mark.asyncio
async def test_list_retryable_failed(db_session: AsyncSession, channel: Channel):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, channel.id)
    run_id = str(run.id)
    await crud.mark_running(db_session, run_id)
    await crud.mark_failed(db_session, run_id, last_error="transient")

    retryable = await crud.list_retryable_failed(db_session)
    assert any(str(item.id) == run_id for item in retryable)


@pytest.mark.asyncio
async def test_create_pending_runs(db_session: AsyncSession, channel: Channel):
    crud = PipelineRunCrud()
    run_ids = await crud.create_pending_runs(db_session, channel.id, 2)
    assert len(run_ids) == 2
    for run_id in run_ids:
        loaded = await crud.get_by_id(db_session, run_id)
        assert loaded is not None
        assert loaded.status == PipelineRunStatus.PENDING.value


@pytest.mark.asyncio
async def test_update_step(db_session: AsyncSession, channel: Channel):
    crud = PipelineRunCrud()
    run = await crud.create_run(db_session, channel.id)
    updated = await crud.update_step(db_session, str(run.id), "script")
    assert updated is not None
    assert updated.current_step == "script"
