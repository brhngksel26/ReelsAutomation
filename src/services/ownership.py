from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.deps import (
    get_channel_crud,
    get_profile_crud,
    get_video_metadata_crud,
)
from src.models.auth import User
from src.models.channel import Channel
from src.models.video import VideoMetadata
from src.protocols.auth import ProfileRepository
from src.protocols.channel import ChannelRepository
from src.protocols.video import VideoMetadataRepository


async def get_user_profile(
    db: AsyncSession,
    user: User,
    *,
    profile_crud: ProfileRepository | None = None,
):
    profile_crud = profile_crud or get_profile_crud()

    profile = await profile_crud.get_by_user_id(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


async def get_owned_channel(
    db: AsyncSession,
    user: User,
    channel_id: int,
    *,
    profile_crud: ProfileRepository | None = None,
    channel_crud: ChannelRepository | None = None,
) -> Channel:
    profile_crud = profile_crud or get_profile_crud()
    channel_crud = channel_crud or get_channel_crud()

    profile = await get_user_profile(db, user, profile_crud=profile_crud)
    channel = await channel_crud.get_owned(db, channel_id, profile.id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


async def get_owned_video(
    db: AsyncSession,
    user: User,
    video_id: int,
    *,
    profile_crud: ProfileRepository | None = None,
    video_metadata_crud: VideoMetadataRepository | None = None,
) -> VideoMetadata:
    profile_crud = profile_crud or get_profile_crud()
    video_metadata_crud = video_metadata_crud or get_video_metadata_crud()

    profile = await get_user_profile(db, user, profile_crud=profile_crud)
    video = await video_metadata_crud.get_owned(db, video_id, profile.id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
