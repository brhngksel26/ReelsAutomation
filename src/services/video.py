from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_exception import CrudIntegrityError
from src.core.deps import get_profile_crud, get_video_metadata_crud
from src.core.enums import GenerationStatus
from src.models.auth import User
from src.models.video import VideoMetadata
from src.protocols.auth import ProfileRepository
from src.protocols.video import VideoMetadataRepository
from src.schemas.video import VideoScheduleIn
from src.services.ownership import get_owned_channel, get_owned_video


async def schedule_video(
    db: AsyncSession,
    user: User,
    data: VideoScheduleIn,
    *,
    video_metadata_crud: VideoMetadataRepository | None = None,
) -> VideoMetadata:
    await get_owned_channel(db, user, data.channel_id)
    crud = video_metadata_crud or get_video_metadata_crud()
    try:
        video = await crud.create(
            db,
            {
                "channel_id": data.channel_id,
                "hook_text": data.hook_text,
                "caption": data.caption,
                "generated_hashtags": data.generated_hashtags,
                "scheduled_at": data.scheduled_at,
                "generation_status": GenerationStatus.PENDING.value,
            },
        )
        from sqlalchemy import event

        from src.tasks.video import generate_video_content_task

        video_id = video.id

        @event.listens_for(db.sync_session, "after_commit", once=True)
        def _enqueue_generation(_session) -> None:
            generate_video_content_task.delay(video_id)

        return video
    except CrudIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def list_upcoming_videos(
    db: AsyncSession,
    user: User,
    skip: int = 0,
    limit: int = 100,
    *,
    profile_crud: ProfileRepository | None = None,
    video_metadata_crud: VideoMetadataRepository | None = None,
) -> list[VideoMetadata]:
    profile_repo = profile_crud or get_profile_crud()
    video_repo = video_metadata_crud or get_video_metadata_crud()
    profile = await profile_repo.get_by_user_id(db, user.id)
    if not profile:
        return []
    return await video_repo.get_upcoming_by_profile(
        db,
        profile.id,
        skip=skip,
        limit=limit,
    )


async def get_video_status(
    db: AsyncSession,
    user: User,
    video_id: int,
    *,
    video_metadata_crud: VideoMetadataRepository | None = None,
) -> VideoMetadata:
    await get_owned_video(db, user, video_id)
    crud = video_metadata_crud or get_video_metadata_crud()
    video = await crud.get_with_publish_statuses(db, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
