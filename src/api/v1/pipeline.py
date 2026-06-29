from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_channel_crud, get_pipeline_run_crud
from src.core.database import build_checkpointer, get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.models.auth import User
from src.pipeline.graph import build_pipeline
from src.schemas.pipeline import (
    PipelineRunOut,
    PipelineStatusOut,
    PipelineTriggerIn,
    PipelineTriggerOut,
)
from src.services.ownership import get_owned_channel
from src.tasks.pipeline import run_channel_pipeline_task
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/pipeline",
    tags=["pipeline"],
)


@router.post(
    "/trigger", response_model=PipelineTriggerOut, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_pipeline(
    data: PipelineTriggerIn,
    user: User = Depends(require_permission(Permission.VIDEO_SCHEDULE)),
    db: AsyncSession = Depends(get_async_session),
    channel_crud=Depends(get_channel_crud),
    pipeline_run_crud=Depends(get_pipeline_run_crud),
):
    await get_owned_channel(db, user, data.channel_id, channel_crud=channel_crud)
    run = await pipeline_run_crud.create_run(db, data.channel_id)
    task = run_channel_pipeline_task.delay(data.channel_id, str(run.id))
    return PipelineTriggerOut(
        message=f"Pipeline triggered for channel {data.channel_id}",
        task_id=task.id,
        run_id=str(run.id),
    )


@router.get("/runs", response_model=list[PipelineRunOut])
async def list_pipeline_runs(
    channel_id: int = Query(gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_permission(Permission.VIDEO_READ)),
    db: AsyncSession = Depends(get_async_session),
    channel_crud=Depends(get_channel_crud),
    pipeline_run_crud=Depends(get_pipeline_run_crud),
):
    await get_owned_channel(db, user, channel_id, channel_crud=channel_crud)
    runs = await pipeline_run_crud.list_by_channel(db, channel_id, limit=limit)
    return [
        PipelineRunOut(
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
        )
        for run in runs
    ]


@router.get("/status/{thread_id}", response_model=PipelineStatusOut)
async def get_pipeline_status(
    thread_id: str,
    _user: User = Depends(require_permission(Permission.VIDEO_READ)),
):
    async with build_checkpointer() as checkpointer:
        pipeline = build_pipeline(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        state = await pipeline.aget_state(config)

    if state is None or not state.values:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    return PipelineStatusOut(
        current_step=state.values.get("current_step"),
        retry_count=state.values.get("retry_count"),
        errors=state.values.get("errors"),
        publish_results=state.values.get("publish_results"),
    )
