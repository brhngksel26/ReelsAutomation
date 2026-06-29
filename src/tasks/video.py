import logging

from src.core.async_run import run_async
from src.core.celery_app import celery_app
from src.core.database import worker_async_session_maker
from src.core.deps import get_video_metadata_crud
from src.core.enums import GenerationStatus
from src.core.unit_of_work import transaction
from src.services.publishing import publish_video_to_platforms

logger = logging.getLogger(__name__)


async def _generate_video_content(video_metadata_id: int) -> None:
    async with worker_async_session_maker() as db:
        async with transaction(db):
            crud = get_video_metadata_crud()
            video = await crud.get_by_id(db, video_metadata_id)
            if not video:
                logger.warning("Video %s not found for generation", video_metadata_id)
                return

            await crud.update_generation_status(
                db, video_metadata_id, GenerationStatus.PROCESSING
            )
            try:
                video_path = f"/storage/videos/{video_metadata_id}.mp4"
                audio_path = f"/storage/audio/{video_metadata_id}.mp3"
                await crud.update_generation_status(
                    db,
                    video_metadata_id,
                    GenerationStatus.COMPLETED,
                    video_path=video_path,
                    audio_path=audio_path,
                )
                logger.info("Video %s generation completed", video_metadata_id)
            except Exception as exc:
                logger.exception("Video %s generation failed", video_metadata_id)
                await crud.update_generation_status(
                    db, video_metadata_id, GenerationStatus.FAILED
                )
                raise exc


async def _publish_to_platforms(video_metadata_id: int) -> None:
    async with worker_async_session_maker() as db:
        async with transaction(db):
            await publish_video_to_platforms(db, video_metadata_id)


async def _check_due_videos() -> None:
    async with worker_async_session_maker() as db:
        async with transaction(db):
            due_videos = await get_video_metadata_crud().get_due_for_publish(db)
            for video in due_videos:
                logger.info("Enqueueing publish for due video %s", video.id)
                publish_to_platforms_task.delay(video.id)


async def _retry_failed_publishes() -> None:
    from src.services import retry_admin as retry_admin_service

    async with worker_async_session_maker() as db:
        async with transaction(db):
            video_ids = await retry_admin_service.list_failed_publish_video_ids(db)

    for video_id in video_ids:
        logger.info("Re-enqueueing publish for failed video %s", video_id)
        retry_admin_service.enqueue_publish_retry(video_id)


@celery_app.task(name="src.tasks.video.generate_video_content_task")
def generate_video_content_task(video_metadata_id: int) -> None:
    run_async(_generate_video_content(video_metadata_id))


@celery_app.task(name="src.tasks.video.publish_to_platforms_task")
def publish_to_platforms_task(video_metadata_id: int) -> None:
    run_async(_publish_to_platforms(video_metadata_id))


@celery_app.task(name="src.tasks.video.check_due_videos")
def check_due_videos() -> None:
    run_async(_check_due_videos())


@celery_app.task(name="src.tasks.video.retry_failed_publishes")
def retry_failed_publishes() -> None:
    run_async(_retry_failed_publishes())
