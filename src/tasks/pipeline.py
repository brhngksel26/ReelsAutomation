import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select

from src.core.async_run import run_async
from src.core.base_exception import LLMProviderUnavailableError, LLMRateLimitError
from src.core.celery_app import celery_app
from src.core.config import settings
from src.core.database import worker_async_session_maker
from src.core.deps import get_pipeline_run_crud
from src.core.enums import SchedulingMode
from src.core.unit_of_work import transaction
from src.integrations.ntfy import (
    send_pipeline_max_retry_alert,
    send_pipeline_stale_alert,
)
from src.models.channel import Channel
from src.pipeline.exceptions import PipelineChannelNotFoundError, PipelineStateError
from src.pipeline.state import PipelineState

logger = logging.getLogger(__name__)

try:
    from src.pipeline.runner import run_channel_pipeline
except ImportError:  # pragma: no cover - graceful fallback until runner exists

    async def run_channel_pipeline(
        channel_id: int,
        run_id: str | None = None,
        *,
        celery_task_id: str | None = None,
    ) -> PipelineState:
        raise RuntimeError("Pipeline runner is not available")


def _is_rss_news_channel(channel: Channel) -> bool:
    mode = channel.scheduling_mode
    if isinstance(mode, SchedulingMode):
        return mode == SchedulingMode.RSS_NEWS
    return mode == SchedulingMode.RSS_NEWS.value


async def _dispatch_due_channel_pipelines() -> None:
    now = datetime.now(timezone.utc)
    current_slot = (now.hour, now.minute)

    async with worker_async_session_maker() as db:
        async with transaction(db):
            result = await db.execute(
                select(Channel).where(
                    and_(
                        Channel.is_active.is_(True),
                        Channel.is_deleted.is_(False),
                    )
                )
            )
            channels = list(result.scalars().all())

    for channel in channels:
        if _is_rss_news_channel(channel):
            continue
        if not channel.posting_hours:
            continue
        if not any(
            (posting_time.hour, posting_time.minute) == current_slot
            for posting_time in channel.posting_hours
        ):
            continue
        logger.info("Enqueueing pipeline for due channel %s", channel.id)
        async with worker_async_session_maker() as db:
            async with transaction(db):
                run = await get_pipeline_run_crud().create_run(db, channel.id)
                run_channel_pipeline_task.delay(channel.id, str(run.id))


async def _retry_stale_pipelines() -> None:
    from src.services import retry_admin as retry_admin_service

    crud = get_pipeline_run_crud()
    async with worker_async_session_maker() as db:
        async with transaction(db):
            stale_running = await crud.list_stale_running(db)
            for run in stale_running:
                await crud.mark_stale(db, str(run.id))
                await send_pipeline_stale_alert(run)

            exhausted = await crud.list_exhausted_retries(db)
            retryable = await crud.list_retryable_stale(
                db
            ) + await crud.list_retryable_failed(db)

    for run in exhausted:
        await send_pipeline_max_retry_alert(run)

    for run in retryable:
        async with worker_async_session_maker() as db:
            async with transaction(db):
                task_id = await retry_admin_service.enqueue_pipeline_retry(
                    db, run, immediate=False
                )
            logger.info(
                "Re-enqueueing pipeline channel_id=%s run_id=%s retry_count=%s task_id=%s",
                run.channel_id,
                run.id,
                run.retry_count + 1,
                task_id,
            )


@celery_app.task(
    bind=True,
    acks_late=True,
    name="src.tasks.pipeline.run_channel_pipeline_task",
    autoretry_for=(
        LLMProviderUnavailableError,
        LLMRateLimitError,
        ConnectionError,
        TimeoutError,
    ),
    dont_autoretry_for=(
        PipelineChannelNotFoundError,
        PipelineStateError,
    ),
    retry_backoff=True,
    retry_backoff_max=settings.PIPELINE_CELERY_RETRY_BACKOFF_MAX,
    max_retries=settings.PIPELINE_CELERY_MAX_RETRIES,
)
def run_channel_pipeline_task(
    self,
    channel_id: int,
    run_id: str | None = None,
) -> None:
    run_async(
        run_channel_pipeline(
            channel_id,
            run_id,
            celery_task_id=self.request.id,
        )
    )


@celery_app.task(name="src.tasks.pipeline.dispatch_due_channel_pipelines")
def dispatch_due_channel_pipelines() -> None:
    run_async(_dispatch_due_channel_pipelines())


@celery_app.task(name="src.tasks.pipeline.retry_stale_pipelines")
def retry_stale_pipelines() -> None:
    run_async(_retry_stale_pipelines())
