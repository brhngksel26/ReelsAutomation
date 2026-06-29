from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_channel_crud, get_platform_config_crud, get_profile_crud
from src.core.database import get_async_session
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.permission import Permission
from src.cruds.auth import ProfileCrud
from src.cruds.channel import ChannelCrud, PlatformConfigCrud
from src.models.auth import User
from src.schemas.platform import PlatformConnectIn, PlatformStatusOut
from src.services import platform as platform_service
from src.utils.require_permission import require_permission

router = APIRouter(
    route_class=ExceptionHandlingRoute,
    prefix="/api/v1/platforms",
    tags=["platforms"],
)


@router.post(
    "/connect", response_model=PlatformStatusOut, status_code=status.HTTP_201_CREATED
)
async def connect_platform(
    data: PlatformConnectIn,
    user: User = Depends(require_permission(Permission.PLATFORM_CONNECT)),
    db: AsyncSession = Depends(get_async_session),
    platform_config_crud: PlatformConfigCrud = Depends(get_platform_config_crud),
):
    return await platform_service.connect_platform(
        db,
        user,
        data,
        platform_config_crud=platform_config_crud,
    )


@router.get("/status", response_model=list[PlatformStatusOut])
async def get_platform_status(
    user: User = Depends(require_permission(Permission.PLATFORM_READ)),
    db: AsyncSession = Depends(get_async_session),
    channel_id: int | None = Query(default=None),
    profile_crud: ProfileCrud = Depends(get_profile_crud),
    channel_crud: ChannelCrud = Depends(get_channel_crud),
    platform_config_crud: PlatformConfigCrud = Depends(get_platform_config_crud),
):
    return await platform_service.get_platform_statuses(
        db,
        user,
        channel_id=channel_id,
        profile_crud=profile_crud,
        channel_crud=channel_crud,
        platform_config_crud=platform_config_crud,
    )
