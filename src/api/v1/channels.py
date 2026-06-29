from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_channel_crud, get_profile_crud
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.cruds.auth import ProfileCrud
from src.cruds.channel import ChannelCrud
from src.models.auth import User
from src.schemas.channel import ChannelCreateIn, ChannelOut, ChannelUpdateIn
from src.services import channel as channel_service
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/channels",
    tags=["channels"],
)


@router.post("/", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: ChannelCreateIn,
    user: User = Depends(require_permission(Permission.CHANNEL_CREATE)),
    db: AsyncSession = Depends(get_async_session),
    profile_crud: ProfileCrud = Depends(get_profile_crud),
    channel_crud: ChannelCrud = Depends(get_channel_crud),
):
    return await channel_service.create_channel(
        db,
        user,
        data,
        profile_crud=profile_crud,
        channel_crud=channel_crud,
    )


@router.get("/", response_model=list[ChannelOut])
async def list_channels(
    user: User = Depends(require_permission(Permission.CHANNEL_READ)),
    db: AsyncSession = Depends(get_async_session),
    skip: int = 0,
    limit: int = 100,
    profile_crud: ProfileCrud = Depends(get_profile_crud),
    channel_crud: ChannelCrud = Depends(get_channel_crud),
):
    return await channel_service.list_channels(
        db,
        user,
        skip=skip,
        limit=limit,
        profile_crud=profile_crud,
        channel_crud=channel_crud,
    )


@router.put("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: int,
    data: ChannelUpdateIn,
    user: User = Depends(require_permission(Permission.CHANNEL_UPDATE)),
    db: AsyncSession = Depends(get_async_session),
    channel_crud: ChannelCrud = Depends(get_channel_crud),
):
    return await channel_service.update_channel(
        db,
        user,
        channel_id,
        data,
        channel_crud=channel_crud,
    )


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: int,
    user: User = Depends(require_permission(Permission.CHANNEL_DELETE)),
    db: AsyncSession = Depends(get_async_session),
    channel_crud: ChannelCrud = Depends(get_channel_crud),
):
    await channel_service.delete_channel(
        db,
        user,
        channel_id,
        channel_crud=channel_crud,
    )
