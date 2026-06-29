from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_profile_crud, get_video_metadata_crud
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.models.auth import User
from src.schemas.video import VideoOut, VideoScheduleIn, VideoStatusOut
from src.services import video as video_service
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/videos",
    tags=["videos"],
)


@router.post("/schedule", response_model=VideoOut, status_code=status.HTTP_201_CREATED)
async def schedule_video(
    data: VideoScheduleIn,
    user: User = Depends(require_permission(Permission.VIDEO_SCHEDULE)),
    db: AsyncSession = Depends(get_async_session),
    video_metadata_crud=Depends(get_video_metadata_crud),
):
    return await video_service.schedule_video(
        db,
        user,
        data,
        video_metadata_crud=video_metadata_crud,
    )


@router.get("/upcoming", response_model=list[VideoOut])
async def list_upcoming_videos(
    user: User = Depends(require_permission(Permission.VIDEO_READ)),
    db: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    profile_crud=Depends(get_profile_crud),
    video_metadata_crud=Depends(get_video_metadata_crud),
):
    return await video_service.list_upcoming_videos(
        db,
        user,
        skip=skip,
        limit=limit,
        profile_crud=profile_crud,
        video_metadata_crud=video_metadata_crud,
    )


@router.get("/{video_id}/status", response_model=VideoStatusOut)
async def get_video_status(
    video_id: int,
    user: User = Depends(require_permission(Permission.VIDEO_READ)),
    db: AsyncSession = Depends(get_async_session),
    video_metadata_crud=Depends(get_video_metadata_crud),
):
    return await video_service.get_video_status(
        db,
        user,
        video_id,
        video_metadata_crud=video_metadata_crud,
    )
