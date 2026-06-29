import asyncio
import logging
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from src.core.config import settings
from src.core.database import build_checkpointer

logger = logging.getLogger(__name__)

celery_app = Celery(
    "reels_automation",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "src.tasks.video",
        "src.tasks.pipeline",
        "src.tasks.rss",
        "src.tasks.health",
        "src.tasks.notifications",
    ],
)

_beat_schedule: dict = {
    "check-due-videos": {
        "task": "src.tasks.video.check_due_videos",
        "schedule": 60.0,
    },
    "dispatch-due-channel-pipelines": {
        "task": "src.tasks.pipeline.dispatch_due_channel_pipelines",
        "schedule": 60.0,
    },
    "retry-stale-pipelines": {
        "task": "src.tasks.pipeline.retry_stale_pipelines",
        "schedule": 300.0,
    },
    "check-beat-health": {
        "task": "src.tasks.health.check_beat_health",
        "schedule": 300.0,
    },
    "retry-failed-publishes": {
        "task": "src.tasks.video.retry_failed_publishes",
        "schedule": crontab(hour=[6, 18], minute=0),
    },
    "send-daily-channel-digests": {
        "task": "src.tasks.notifications.send_daily_channel_digests",
        "schedule": crontab(hour=20, minute=0),
    },
}

if settings.RSS_ENABLED:
    _beat_schedule["scrape-rss-feeds-daily"] = {
        "task": "src.tasks.rss.scrape_rss_feeds",
        "schedule": crontab(hour=settings.RSS_SCRAPE_HOUR, minute=0),
    }

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule=_beat_schedule,
    beat_schedule_filename=os.getenv(
        "CELERY_BEAT_SCHEDULE_FILENAME",
        "celerybeat-schedule",
    ),
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={
        "visibility_timeout": settings.PIPELINE_VISIBILITY_TIMEOUT,
    },
)


@worker_ready.connect
def setup_langgraph_checkpointer(**_kwargs) -> None:
    async def _setup() -> None:
        async with build_checkpointer() as checkpointer:
            await checkpointer.setup()
        logger.info("LangGraph checkpointer tables initialized")

    asyncio.run(_setup())


@worker_ready.connect
def trigger_stale_pipeline_scan_on_startup(**_kwargs) -> None:
    from src.tasks.pipeline import retry_stale_pipelines

    retry_stale_pipelines.delay()
    logger.info("Triggered stale pipeline scan on worker startup")
