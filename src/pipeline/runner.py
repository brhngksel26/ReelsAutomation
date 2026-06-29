from __future__ import annotations

import logging
from uuid import uuid4

from src.core.database import build_checkpointer, pipeline_async_session_maker
from src.core.deps import get_pipeline_run_crud
from src.core.unit_of_work import transaction
from src.cruds.rss import release_consumption
from src.integrations.ntfy import (
    send_pipeline_notification,
    should_send_pipeline_notification,
)
from src.pipeline.exceptions import PipelineStateError
from src.pipeline.graph import build_pipeline
from src.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def _build_thread_id(channel_id: int, run_id: str) -> str:
    return f"channel-{channel_id}-{run_id}"


def _initial_state(channel_id: int, run_id: str | None = None) -> PipelineState:
    return {
        "channel_id": channel_id,
        "past_performance": [],
        "video_idea": None,
        "video_script": None,
        "idea_is_acceptable": False,
        "idea_score": 0,
        "video_metadata_id": None,
        "video_path": None,
        "publish_results": [],
        "retry_count": 0,
        "current_step": "started",
        "errors": [],
        "run_id": run_id or str(uuid4()),
        "selected_news_item": None,
        "news_required": False,
        "news_consumption_id": None,
    }


async def run_channel_pipeline(
    channel_id: int,
    run_id: str | None = None,
    *,
    celery_task_id: str | None = None,
) -> PipelineState:
    crud = get_pipeline_run_crud()
    registry_run_id: str
    thread_id: str
    retry_count = 0

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            if run_id:
                existing = await crud.get_by_id(db, run_id)
                if not existing:
                    raise PipelineStateError(f"Pipeline run {run_id} not found")
                if existing.channel_id != channel_id:
                    raise PipelineStateError(
                        f"Pipeline run {run_id} does not belong to channel {channel_id}"
                    )
                registry_run_id = str(existing.id)
                thread_id = existing.thread_id
                retry_count = existing.retry_count
            else:
                created = await crud.create_run(db, channel_id)
                registry_run_id = str(created.id)
                thread_id = created.thread_id

            await crud.mark_running(db, registry_run_id, celery_task_id=celery_task_id)

    initial_state = _initial_state(channel_id, registry_run_id)
    initial_state["retry_count"] = retry_count
    config = {"configurable": {"thread_id": thread_id}}

    async with build_checkpointer() as checkpointer:
        await checkpointer.setup()
        graph = build_pipeline(checkpointer)
        result: PipelineState | None = None
        pipeline_error: str | None = None
        resumed = False

        try:
            if run_id:
                checkpoint = await graph.aget_state(config)
                if checkpoint is not None and checkpoint.values:
                    async with pipeline_async_session_maker() as db:
                        async with transaction(db):
                            step = checkpoint.values.get("current_step")
                            if step:
                                await crud.update_step(db, registry_run_id, step)
                    result = await graph.ainvoke(None, config=config)
                    resumed = True

            if result is None:
                if run_id and not resumed:
                    async with pipeline_async_session_maker() as db:
                        async with transaction(db):
                            updated = await crud.increment_retry_count(
                                db, registry_run_id
                            )
                            if updated:
                                retry_count = updated.retry_count
                    initial_state["retry_count"] = retry_count
                    logger.warning(
                        "Pipeline resume fallback channel_id=%s run_id=%s retry_count=%s",
                        channel_id,
                        registry_run_id,
                        retry_count,
                    )
                result = await graph.ainvoke(initial_state, config=config)

            async with pipeline_async_session_maker() as db:
                async with transaction(db):
                    await crud.mark_completed(
                        db,
                        registry_run_id,
                        current_step=result.get("current_step"),
                        video_metadata_id=result.get("video_metadata_id"),
                        news_consumption_id=result.get("news_consumption_id"),
                    )
        except Exception as exc:
            pipeline_error = str(exc)
            async with pipeline_async_session_maker() as db:
                async with transaction(db):
                    consumption_id = None
                    if result is not None:
                        consumption_id = result.get("news_consumption_id")
                    if consumption_id is None:
                        consumption_id = initial_state.get("news_consumption_id")
                    if consumption_id is not None:
                        await release_consumption(db, consumption_id)
                    await crud.mark_failed(
                        db,
                        registry_run_id,
                        last_error=pipeline_error,
                        current_step=(result or initial_state).get("current_step"),
                    )
            raise
        finally:
            state = result or initial_state
            if should_send_pipeline_notification(state, pipeline_error=pipeline_error):
                await send_pipeline_notification(state, pipeline_error=pipeline_error)

    logger.info(
        "run_channel_pipeline channel_id=%s run_id=%s thread_id=%s step=%s resumed=%s",
        channel_id,
        registry_run_id,
        thread_id,
        result.get("current_step"),
        resumed,
    )
    assert result is not None
    return result
