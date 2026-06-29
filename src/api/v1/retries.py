from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_pipeline_run_crud, get_video_publish_status_crud
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.models.auth import User
from src.schemas.retry import FailedPublishOut, RetryablePipelineRunOut, RetryEnqueueOut
from src.services import retry_admin as retry_admin_service
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/retries",
    tags=["retries"],
)


@router.get("/pipelines", response_model=list[RetryablePipelineRunOut])
async def list_retryable_pipelines(
    channel_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_permission(Permission.VIDEO_READ)),
    db: AsyncSession = Depends(get_async_session),
    pipeline_run_crud=Depends(get_pipeline_run_crud),
):
    return await retry_admin_service.list_retryable_pipeline_runs(
        db,
        user,
        channel_id=channel_id,
        limit=limit,
        pipeline_run_crud=pipeline_run_crud,
    )


@router.get("/publishes", response_model=list[FailedPublishOut])
async def list_failed_publishes(
    channel_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_permission(Permission.VIDEO_READ)),
    db: AsyncSession = Depends(get_async_session),
    video_publish_status_crud=Depends(get_video_publish_status_crud),
):
    return await retry_admin_service.list_failed_publishes(
        db,
        user,
        channel_id=channel_id,
        limit=limit,
        video_publish_status_crud=video_publish_status_crud,
    )


@router.post(
    "/pipelines/retry-all",
    response_model=RetryEnqueueOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_all_pipelines(
    channel_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_permission(Permission.VIDEO_SCHEDULE)),
    db: AsyncSession = Depends(get_async_session),
    pipeline_run_crud=Depends(get_pipeline_run_crud),
):
    return await retry_admin_service.retry_all_pipeline_runs(
        db,
        user,
        channel_id=channel_id,
        limit=limit,
        pipeline_run_crud=pipeline_run_crud,
    )


@router.post(
    "/pipelines/{run_id}",
    response_model=RetryEnqueueOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_pipeline(
    run_id: str,
    user: User = Depends(require_permission(Permission.VIDEO_SCHEDULE)),
    db: AsyncSession = Depends(get_async_session),
    pipeline_run_crud=Depends(get_pipeline_run_crud),
):
    return await retry_admin_service.retry_pipeline_run(
        db,
        user,
        run_id,
        pipeline_run_crud=pipeline_run_crud,
    )


@router.post(
    "/publishes/retry-all",
    response_model=RetryEnqueueOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_all_publishes(
    channel_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_permission(Permission.VIDEO_SCHEDULE)),
    db: AsyncSession = Depends(get_async_session),
    video_publish_status_crud=Depends(get_video_publish_status_crud),
):
    return await retry_admin_service.retry_all_failed_publishes(
        db,
        user,
        channel_id=channel_id,
        limit=limit,
        video_publish_status_crud=video_publish_status_crud,
    )


@router.post(
    "/publishes/{video_id}",
    response_model=RetryEnqueueOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_publish(
    video_id: int,
    user: User = Depends(require_permission(Permission.VIDEO_SCHEDULE)),
    db: AsyncSession = Depends(get_async_session),
    video_publish_status_crud=Depends(get_video_publish_status_crud),
):
    return await retry_admin_service.retry_publish(
        db,
        user,
        video_id,
        video_publish_status_crud=video_publish_status_crud,
    )
