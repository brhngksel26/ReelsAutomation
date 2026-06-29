from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_exception import CrudIntegrityError
from src.core.deps import get_channel_crud, get_platform_config_crud, get_profile_crud
from src.core.enums import PlatformStatus
from src.domain.platform import validate_platform_specific_settings
from src.models.auth import User
from src.models.channel import PlatformConfig
from src.protocols.auth import ProfileRepository
from src.protocols.channel import ChannelRepository, PlatformConfigRepository
from src.schemas.platform import PlatformConnectIn
from src.schemas.platform_credentials import validate_credentials_json
from src.services.ownership import get_owned_channel


async def connect_platform(
    db: AsyncSession,
    user: User,
    data: PlatformConnectIn,
    *,
    platform_config_crud: PlatformConfigRepository | None = None,
) -> PlatformConfig:
    platform_config_crud = platform_config_crud or get_platform_config_crud()
    await get_owned_channel(db, user, data.channel_id)
    existing = await platform_config_crud.get_by_channel_and_platform(
        db,
        data.channel_id,
        data.platform_type.value,
    )
    try:
        validated_credentials = validate_credentials_json(
            data.platform_type,
            data.credentials_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        validated_settings = validate_platform_specific_settings(
            data.platform_specific_settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = {
        "channel_id": data.channel_id,
        "platform_type": data.platform_type.value,
        "credentials_json": validated_credentials,
        "platform_specific_settings": validated_settings,
        "status": PlatformStatus.CONNECTED.value,
    }
    try:
        if existing:
            updated = await platform_config_crud.update(db, existing.id, payload)
            if not updated:
                raise HTTPException(status_code=404, detail="Platform config not found")
            return updated
        return await platform_config_crud.create(db, payload)
    except CrudIntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def get_platform_statuses(
    db: AsyncSession,
    user: User,
    channel_id: int | None = None,
    *,
    profile_crud: ProfileRepository | None = None,
    channel_crud: ChannelRepository | None = None,
    platform_config_crud: PlatformConfigRepository | None = None,
) -> list[PlatformConfig]:
    profile_crud = profile_crud or get_profile_crud()
    channel_crud = channel_crud or get_channel_crud()
    platform_config_crud = platform_config_crud or get_platform_config_crud()
    profile = await profile_crud.get_by_user_id(db, user.id)
    if not profile:
        return []

    if channel_id is not None:
        await get_owned_channel(db, user, channel_id)
        channels = [await channel_crud.get_owned(db, channel_id, profile.id)]
        channel_ids = [c.id for c in channels if c]
    else:
        channels = await channel_crud.get_by_profile(db, profile.id)
        channel_ids = [c.id for c in channels]

    return await platform_config_crud.get_by_profile_channels(db, channel_ids)
