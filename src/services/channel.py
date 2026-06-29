from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_exception import CrudIntegrityError
from src.core.deps import get_channel_crud, get_profile_crud
from src.models.auth import User
from src.models.channel import Channel
from src.protocols.auth import ProfileRepository
from src.protocols.channel import ChannelRepository
from src.schemas.channel import ChannelCreateIn, ChannelUpdateIn


async def create_channel(
    db: AsyncSession,
    user: User,
    data: ChannelCreateIn,
    *,
    profile_crud: ProfileRepository | None = None,
    channel_crud: ChannelRepository | None = None,
) -> Channel:
    profile_crud = profile_crud or get_profile_crud()
    channel_crud = channel_crud or get_channel_crud()
    profile = await profile_crud.get_by_user_id(db, user.id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        return await channel_crud.create(
            db,
            {"profile_id": profile.id, **data.model_dump()},
        )
    except CrudIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def list_channels(
    db: AsyncSession,
    user: User,
    skip: int = 0,
    limit: int = 100,
    *,
    profile_crud: ProfileRepository | None = None,
    channel_crud: ChannelRepository | None = None,
) -> list[Channel]:
    profile_crud = profile_crud or get_profile_crud()
    channel_crud = channel_crud or get_channel_crud()
    profile = await profile_crud.get_by_user_id(db, user.id)
    if not profile:
        return []
    return await channel_crud.get_by_profile(db, profile.id, skip=skip, limit=limit)


async def update_channel(
    db: AsyncSession,
    user: User,
    channel_id: int,
    data: ChannelUpdateIn,
    *,
    channel_crud: ChannelRepository | None = None,
) -> Channel:
    from src.services.ownership import get_owned_channel

    channel_crud = channel_crud or get_channel_crud()
    channel = await get_owned_channel(db, user, channel_id)
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return channel
    updated = await channel_crud.update(db, channel.id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail="Channel not found")
    return updated


async def delete_channel(
    db: AsyncSession,
    user: User,
    channel_id: int,
    *,
    channel_crud: ChannelRepository | None = None,
) -> bool:
    from src.services.ownership import get_owned_channel

    channel_crud = channel_crud or get_channel_crud()
    channel = await get_owned_channel(db, user, channel_id)
    return await channel_crud.delete(db, channel.id)
