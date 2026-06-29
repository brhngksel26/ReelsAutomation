from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.base_crud import BaseCrudService
from src.core.enums import GenerationStatus, PublishStatus
from src.models.channel import Channel
from src.models.video import VideoMetadata, VideoPublishStatus


class VideoMetadataCrud(BaseCrudService):
    def __init__(self):
        super().__init__(VideoMetadata)

    async def get_upcoming_by_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[VideoMetadata]:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(VideoMetadata)
            .join(Channel, VideoMetadata.channel_id == Channel.id)
            .where(
                and_(
                    Channel.profile_id == profile_id,
                    Channel.is_deleted.is_(False),
                    VideoMetadata.is_deleted.is_(False),
                    VideoMetadata.scheduled_at >= now,
                )
            )
            .order_by(VideoMetadata.scheduled_at.asc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_with_publish_statuses(
        self,
        db: AsyncSession,
        video_id: int,
    ) -> VideoMetadata | None:
        result = await db.execute(
            select(VideoMetadata)
            .options(selectinload(VideoMetadata.publish_statuses))
            .where(
                and_(
                    VideoMetadata.id == video_id,
                    VideoMetadata.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_recent_published_by_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        limit: int = 5,
    ) -> list[VideoMetadata]:
        published_video_ids = (
            select(VideoPublishStatus.video_id)
            .where(
                and_(
                    VideoPublishStatus.publish_status == PublishStatus.PUBLISHED.value,
                    VideoPublishStatus.is_deleted.is_(False),
                )
            )
            .distinct()
        )
        result = await db.execute(
            select(VideoMetadata)
            .where(
                and_(
                    VideoMetadata.channel_id == channel_id,
                    VideoMetadata.is_deleted.is_(False),
                    VideoMetadata.id.in_(published_video_ids),
                )
            )
            .order_by(VideoMetadata.created_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_due_for_publish(self, db: AsyncSession) -> list[VideoMetadata]:
        now = datetime.now(timezone.utc)
        published_subq = (
            select(VideoPublishStatus.video_id)
            .where(
                and_(
                    VideoPublishStatus.publish_status == PublishStatus.PUBLISHED.value,
                    VideoPublishStatus.is_deleted.is_(False),
                )
            )
            .distinct()
        )
        result = await db.execute(
            select(VideoMetadata).where(
                and_(
                    VideoMetadata.scheduled_at <= now,
                    VideoMetadata.generation_status == GenerationStatus.COMPLETED.value,
                    VideoMetadata.is_deleted.is_(False),
                    VideoMetadata.id.not_in(published_subq),
                )
            )
        )
        return list(result.scalars().all())

    async def update_generation_status(
        self,
        db: AsyncSession,
        video_id: int,
        status: GenerationStatus,
        *,
        video_path: str | None = None,
        audio_path: str | None = None,
    ) -> VideoMetadata | None:
        data: dict = {"generation_status": status.value}
        if video_path is not None:
            data["video_path"] = video_path
        if audio_path is not None:
            data["audio_path"] = audio_path
        return await self.update(db, video_id, data)

    async def get_owned(
        self,
        db: AsyncSession,
        video_id: int,
        profile_id: int,
    ) -> VideoMetadata | None:
        result = await db.execute(
            select(VideoMetadata)
            .join(Channel, VideoMetadata.channel_id == Channel.id)
            .where(
                and_(
                    VideoMetadata.id == video_id,
                    Channel.profile_id == profile_id,
                    Channel.is_deleted.is_(False),
                    VideoMetadata.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()


class VideoPublishStatusCrud(BaseCrudService):
    def __init__(self):
        super().__init__(VideoPublishStatus)

    async def get_by_video_id(
        self,
        db: AsyncSession,
        video_id: int,
    ) -> list[VideoPublishStatus]:
        result = await db.execute(
            select(VideoPublishStatus).where(
                and_(
                    VideoPublishStatus.video_id == video_id,
                    VideoPublishStatus.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())

    async def upsert_for_platform(
        self,
        db: AsyncSession,
        video_id: int,
        platform_type: str,
        publish_status: PublishStatus,
        *,
        platform_video_id: str | None = None,
        error_log: str | None = None,
        published_at: datetime | None = None,
    ) -> VideoPublishStatus:
        result = await db.execute(
            select(VideoPublishStatus).where(
                and_(
                    VideoPublishStatus.video_id == video_id,
                    VideoPublishStatus.platform_type == platform_type,
                    VideoPublishStatus.is_deleted.is_(False),
                )
            )
        )
        existing = result.scalar_one_or_none()
        payload = {
            "publish_status": publish_status.value,
            "platform_video_id": platform_video_id,
            "error_log": error_log,
            "published_at": published_at,
        }
        if existing:
            updated = await self.update(db, existing.id, payload)
            return updated
        return await self.create(
            db,
            {
                "video_id": video_id,
                "platform_type": platform_type,
                **payload,
            },
        )

    async def list_failed_for_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        *,
        channel_id: int | None = None,
        limit: int = 100,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]:
        conditions = [
            Channel.profile_id == profile_id,
            Channel.is_deleted.is_(False),
            VideoMetadata.is_deleted.is_(False),
            VideoMetadata.generation_status == GenerationStatus.COMPLETED.value,
            VideoPublishStatus.is_deleted.is_(False),
            VideoPublishStatus.publish_status == PublishStatus.FAILED.value,
        ]
        if channel_id is not None:
            conditions.append(VideoMetadata.channel_id == channel_id)

        result = await db.execute(
            select(VideoMetadata, VideoPublishStatus)
            .join(Channel, VideoMetadata.channel_id == Channel.id)
            .join(
                VideoPublishStatus,
                VideoPublishStatus.video_id == VideoMetadata.id,
            )
            .where(and_(*conditions))
            .order_by(VideoMetadata.id.desc())
            .limit(limit)
        )
        return list(result.all())

    async def list_failed_video_ids(self, db: AsyncSession) -> list[int]:
        result = await db.execute(
            select(VideoMetadata.id)
            .join(
                VideoPublishStatus,
                VideoPublishStatus.video_id == VideoMetadata.id,
            )
            .where(
                and_(
                    VideoMetadata.generation_status == GenerationStatus.COMPLETED.value,
                    VideoMetadata.is_deleted.is_(False),
                    VideoPublishStatus.is_deleted.is_(False),
                    VideoPublishStatus.publish_status == PublishStatus.FAILED.value,
                )
            )
            .distinct()
        )
        return list(result.scalars().all())

    async def list_published_in_window(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]:
        result = await db.execute(
            select(VideoMetadata, VideoPublishStatus)
            .join(
                VideoPublishStatus,
                VideoPublishStatus.video_id == VideoMetadata.id,
            )
            .where(
                and_(
                    VideoMetadata.channel_id == channel_id,
                    VideoMetadata.is_deleted.is_(False),
                    VideoPublishStatus.is_deleted.is_(False),
                    VideoPublishStatus.publish_status == PublishStatus.PUBLISHED.value,
                    VideoPublishStatus.published_at.is_not(None),
                    VideoPublishStatus.published_at >= since,
                    VideoPublishStatus.published_at < until,
                )
            )
            .order_by(VideoPublishStatus.published_at.desc())
        )
        return list(result.all())

    async def list_failed_in_window(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        since: datetime,
        until: datetime,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]:
        result = await db.execute(
            select(VideoMetadata, VideoPublishStatus)
            .join(
                VideoPublishStatus,
                VideoPublishStatus.video_id == VideoMetadata.id,
            )
            .where(
                and_(
                    VideoMetadata.channel_id == channel_id,
                    VideoMetadata.is_deleted.is_(False),
                    VideoPublishStatus.is_deleted.is_(False),
                    VideoPublishStatus.publish_status == PublishStatus.FAILED.value,
                    VideoPublishStatus.updated_date >= since,
                    VideoPublishStatus.updated_date < until,
                )
            )
            .order_by(VideoPublishStatus.updated_date.desc())
        )
        return list(result.all())

    async def list_failed_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        limit: int = 100,
    ) -> list[tuple[VideoMetadata, VideoPublishStatus]]:
        result = await db.execute(
            select(VideoMetadata, VideoPublishStatus)
            .join(
                VideoPublishStatus,
                VideoPublishStatus.video_id == VideoMetadata.id,
            )
            .where(
                and_(
                    VideoMetadata.channel_id == channel_id,
                    VideoMetadata.is_deleted.is_(False),
                    VideoMetadata.generation_status == GenerationStatus.COMPLETED.value,
                    VideoPublishStatus.is_deleted.is_(False),
                    VideoPublishStatus.publish_status == PublishStatus.FAILED.value,
                )
            )
            .order_by(VideoMetadata.id.desc())
            .limit(limit)
        )
        return list(result.all())
