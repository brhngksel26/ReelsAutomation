from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.base_crud import BaseCrudService
from src.models.channel import Channel, PlatformConfig


class ChannelCrud(BaseCrudService):
    def __init__(self):
        super().__init__(Channel)

    async def get_by_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Channel]:
        result = await db.execute(
            select(Channel)
            .where(
                and_(
                    Channel.profile_id == profile_id,
                    Channel.is_deleted.is_(False),
                )
            )
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_owned(
        self,
        db: AsyncSession,
        channel_id: int,
        profile_id: int,
    ) -> Channel | None:
        result = await db.execute(
            select(Channel).where(
                and_(
                    Channel.id == channel_id,
                    Channel.profile_id == profile_id,
                    Channel.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_active(self, db: AsyncSession) -> list[Channel]:
        result = await db.execute(
            select(Channel)
            .where(
                and_(
                    Channel.is_active.is_(True),
                    Channel.is_deleted.is_(False),
                )
            )
            .order_by(Channel.id.asc())
        )
        return list(result.scalars().all())


class PlatformConfigCrud(BaseCrudService):
    def __init__(self):
        super().__init__(PlatformConfig)

    async def get_by_channel_and_platform(
        self,
        db: AsyncSession,
        channel_id: int,
        platform_type: str,
    ) -> PlatformConfig | None:
        result = await db.execute(
            select(PlatformConfig).where(
                and_(
                    PlatformConfig.channel_id == channel_id,
                    PlatformConfig.platform_type == platform_type,
                    PlatformConfig.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_profile_channels(
        self,
        db: AsyncSession,
        channel_ids: list[int],
    ) -> list[PlatformConfig]:
        if not channel_ids:
            return []
        result = await db.execute(
            select(PlatformConfig).where(
                and_(
                    PlatformConfig.channel_id.in_(channel_ids),
                    PlatformConfig.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_channel_id(
        self,
        db: AsyncSession,
        channel_id: int,
    ) -> list[PlatformConfig]:
        result = await db.execute(
            select(PlatformConfig).where(
                and_(
                    PlatformConfig.channel_id == channel_id,
                    PlatformConfig.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())
