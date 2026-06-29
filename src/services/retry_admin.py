from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.deps import (
    get_pipeline_run_crud,
    get_video_metadata_crud,
    get_video_publish_status_crud,
)
from src.core.enums import GenerationStatus, PipelineRunStatus, PublishStatus
from src.models.auth import User
from src.models.pipeline_run import PipelineRun
from src.models.video import VideoMetadata, VideoPublishStatus
from src.protocols.pipeline import PipelineRunRepository
from src.protocols.video import VideoMetadataRepository, VideoPublishStatusRepository
from src.schemas.retry import FailedPublishOut, RetryablePipelineRunOut, RetryEnqueueOut
from src.services.ownership import get_owned_channel, get_user_profile

_RETRYABLE_PIPELINE_STATUSES = frozenset(
    {
        PipelineRunStatus.FAILED.value,
        PipelineRunStatus.STALE.value,
    }
)


def _pipeline_retry_block_reason(run: PipelineRun) -> str | None:
    if run.retry_count >= settings.PIPELINE_MAX_RETRIES:
        return f"run {run.id}: max retries exceeded"
    if run.status not in _RETRYABLE_PIPELINE_STATUSES:
        return f"run {run.id}: status is {run.status}"
    return None


def _publish_retry_block_reason(
    video: VideoMetadata,
    statuses: list[VideoPublishStatus],
) -> str | None:
    if video.generation_status != GenerationStatus.COMPLETED.value:
        return f"video {video.id}: generation_status is {video.generation_status}"
    failed_statuses = [
        status
        for status in statuses
        if status.publish_status == PublishStatus.FAILED.value
    ]
    if not failed_statuses:
        if any(s.publish_status == PublishStatus.PUBLISHED.value for s in statuses):
            return f"video {video.id}: already published"
        return f"video {video.id}: no failed publish status"
    return None


def _to_pipeline_run_out(run: PipelineRun) -> RetryablePipelineRunOut:
    return RetryablePipelineRunOut(
        id=str(run.id),
        channel_id=run.channel_id,
        thread_id=run.thread_id,
        status=run.status,
        current_step=run.current_step,
        celery_task_id=run.celery_task_id,
        video_metadata_id=run.video_metadata_id,
        news_consumption_id=run.news_consumption_id,
        retry_count=run.retry_count,
        last_error=run.last_error,
        started_at=run.started_at,
        updated_at=run.updated_at,
        completed_at=run.completed_at,
        retryable=True,
    )


def _to_failed_publish_out(
    video: VideoMetadata,
    status: VideoPublishStatus,
) -> FailedPublishOut:
    return FailedPublishOut(
        video_id=video.id,
        channel_id=video.channel_id,
        platform_type=status.platform_type,
        publish_status=status.publish_status,
        error_log=status.error_log,
        hook_text=video.hook_text,
        video_path=video.video_path,
    )


async def _resolve_channel_filter(
    db: AsyncSession,
    user: User,
    channel_id: int | None,
) -> int | None:
    if channel_id is None:
        return None
    await get_owned_channel(db, user, channel_id)
    return channel_id


async def list_retryable_pipeline_runs(
    db: AsyncSession,
    user: User,
    *,
    channel_id: int | None = None,
    limit: int = 100,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> list[RetryablePipelineRunOut]:
    profile = await get_user_profile(db, user)
    resolved_channel_id = await _resolve_channel_filter(db, user, channel_id)
    crud = pipeline_run_crud or get_pipeline_run_crud()
    runs = await crud.list_retryable_for_profile(
        db,
        profile.id,
        channel_id=resolved_channel_id,
        limit=limit,
    )
    return [_to_pipeline_run_out(run) for run in runs]


async def list_failed_publishes(
    db: AsyncSession,
    user: User,
    *,
    channel_id: int | None = None,
    limit: int = 100,
    video_publish_status_crud: VideoPublishStatusRepository | None = None,
) -> list[FailedPublishOut]:
    profile = await get_user_profile(db, user)
    resolved_channel_id = await _resolve_channel_filter(db, user, channel_id)
    crud = video_publish_status_crud or get_video_publish_status_crud()
    rows = await crud.list_failed_for_profile(
        db,
        profile.id,
        channel_id=resolved_channel_id,
        limit=limit,
    )
    return [_to_failed_publish_out(video, status) for video, status in rows]


async def enqueue_pipeline_retry(
    db: AsyncSession,
    run: PipelineRun,
    *,
    immediate: bool = False,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> str:
    from src.tasks.pipeline import run_channel_pipeline_task

    block_reason = _pipeline_retry_block_reason(run)
    if block_reason:
        raise HTTPException(status_code=409, detail=block_reason)

    crud = pipeline_run_crud or get_pipeline_run_crud()
    countdown_base = run.retry_count
    await crud.increment_retry_count(db, str(run.id))
    await crud.reset_for_retry(db, str(run.id))

    countdown = (
        0
        if immediate
        else min(
            2**countdown_base * 60,
            settings.PIPELINE_CELERY_RETRY_BACKOFF_MAX,
        )
    )
    result = run_channel_pipeline_task.apply_async(
        args=[run.channel_id, str(run.id)],
        countdown=countdown,
        queue="pipeline",
    )
    return str(result.id)


async def enqueue_publish_retry(video_id: int) -> str:
    from src.tasks.video import publish_to_platforms_task

    result = publish_to_platforms_task.delay(video_id)
    return str(result.id)


async def retry_pipeline_run(
    db: AsyncSession,
    user: User,
    run_id: str,
    *,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> RetryEnqueueOut:
    profile = await get_user_profile(db, user)
    crud = pipeline_run_crud or get_pipeline_run_crud()
    run = await crud.get_for_profile(db, run_id, profile.id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    task_id = await enqueue_pipeline_retry(
        db,
        run,
        immediate=True,
        pipeline_run_crud=crud,
    )
    return RetryEnqueueOut(
        message="Pipeline retry enqueued",
        enqueued=1,
        skipped=0,
        task_ids=[task_id],
        run_ids=[str(run.id)],
    )


async def retry_all_pipeline_runs(
    db: AsyncSession,
    user: User,
    *,
    channel_id: int | None = None,
    limit: int = 100,
    pipeline_run_crud: PipelineRunRepository | None = None,
) -> RetryEnqueueOut:
    profile = await get_user_profile(db, user)
    resolved_channel_id = await _resolve_channel_filter(db, user, channel_id)
    crud = pipeline_run_crud or get_pipeline_run_crud()
    runs = await crud.list_retryable_for_profile(
        db,
        profile.id,
        channel_id=resolved_channel_id,
        limit=limit,
    )

    enqueued = 0
    skipped = 0
    skipped_reasons: list[str] = []
    task_ids: list[str] = []
    run_ids: list[str] = []

    for run in runs:
        block_reason = _pipeline_retry_block_reason(run)
        if block_reason:
            skipped += 1
            skipped_reasons.append(block_reason)
            continue
        task_id = await enqueue_pipeline_retry(
            db,
            run,
            immediate=True,
            pipeline_run_crud=crud,
        )
        enqueued += 1
        task_ids.append(task_id)
        run_ids.append(str(run.id))

    return RetryEnqueueOut(
        message="Pipeline retries processed",
        enqueued=enqueued,
        skipped=skipped,
        skipped_reasons=skipped_reasons,
        task_ids=task_ids,
        run_ids=run_ids,
    )


async def retry_publish(
    db: AsyncSession,
    user: User,
    video_id: int,
    *,
    video_publish_status_crud: VideoPublishStatusRepository | None = None,
) -> RetryEnqueueOut:
    video = await get_owned_video_for_retry(db, user, video_id)
    crud = video_publish_status_crud or get_video_publish_status_crud()
    statuses = await crud.get_by_video_id(db, video_id)
    block_reason = _publish_retry_block_reason(video, statuses)
    if block_reason:
        raise HTTPException(status_code=409, detail=block_reason)

    task_id = await enqueue_publish_retry(video_id)
    return RetryEnqueueOut(
        message="Publish retry enqueued",
        enqueued=1,
        skipped=0,
        task_ids=[task_id],
        video_ids=[video_id],
    )


async def retry_all_failed_publishes(
    db: AsyncSession,
    user: User,
    *,
    channel_id: int | None = None,
    limit: int = 100,
    video_publish_status_crud: VideoPublishStatusRepository | None = None,
) -> RetryEnqueueOut:
    profile = await get_user_profile(db, user)
    resolved_channel_id = await _resolve_channel_filter(db, user, channel_id)
    crud = video_publish_status_crud or get_video_publish_status_crud()
    rows = await crud.list_failed_for_profile(
        db,
        profile.id,
        channel_id=resolved_channel_id,
        limit=limit,
    )

    enqueued = 0
    skipped = 0
    skipped_reasons: list[str] = []
    task_ids: list[str] = []
    video_ids: list[int] = []
    seen_video_ids: set[int] = set()

    for video, _status in rows:
        if video.id in seen_video_ids:
            continue
        seen_video_ids.add(video.id)
        statuses = await crud.get_by_video_id(db, video.id)
        block_reason = _publish_retry_block_reason(video, statuses)
        if block_reason:
            skipped += 1
            skipped_reasons.append(block_reason)
            continue
        task_id = await enqueue_publish_retry(video.id)
        enqueued += 1
        task_ids.append(task_id)
        video_ids.append(video.id)

    return RetryEnqueueOut(
        message="Publish retries processed",
        enqueued=enqueued,
        skipped=skipped,
        skipped_reasons=skipped_reasons,
        task_ids=task_ids,
        video_ids=video_ids,
    )


async def get_owned_video_for_retry(
    db: AsyncSession,
    user: User,
    video_id: int,
    *,
    video_metadata_crud: VideoMetadataRepository | None = None,
) -> VideoMetadata:
    profile = await get_user_profile(db, user)
    crud = video_metadata_crud or get_video_metadata_crud()
    video = await crud.get_owned(db, video_id, profile.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


async def list_failed_publish_video_ids(
    db: AsyncSession,
    *,
    video_publish_status_crud: VideoPublishStatusRepository | None = None,
) -> list[int]:
    crud = video_publish_status_crud or get_video_publish_status_crud()
    return await crud.list_failed_video_ids(db)
