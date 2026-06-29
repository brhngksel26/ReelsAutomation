from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.enums import PipelineRunStatus
from src.models.channel import Channel
from src.models.pipeline_run import PipelineRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_run_id(run_id: str | UUID) -> UUID:
    return run_id if isinstance(run_id, UUID) else UUID(str(run_id))


def _utc_today_start() -> datetime:
    now = _utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class PipelineRunCrud:
    async def create_run(self, db: AsyncSession, channel_id: int) -> PipelineRun:
        from uuid import uuid4

        run_uuid = uuid4()
        now = _utcnow()
        run = PipelineRun(
            id=run_uuid,
            channel_id=channel_id,
            thread_id=f"channel-{channel_id}-{run_uuid}",
            status=PipelineRunStatus.PENDING.value,
            retry_count=0,
            updated_at=now,
        )
        db.add(run)
        await db.flush()
        await db.refresh(run)
        return run

    async def create_pending_runs(
        self,
        db: AsyncSession,
        channel_id: int,
        count: int,
    ) -> list[str]:
        run_ids: list[str] = []
        for _ in range(count):
            run = await self.create_run(db, channel_id)
            run_ids.append(str(run.id))
        return run_ids

    async def list_by_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        limit: int = 20,
    ) -> list[PipelineRun]:
        result = await db.execute(
            select(PipelineRun)
            .where(PipelineRun.channel_id == channel_id)
            .order_by(PipelineRun.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_scheduled_today(self, db: AsyncSession, channel_id: int) -> int:
        today_start = _utc_today_start()
        result = await db.execute(
            select(func.count())
            .select_from(PipelineRun)
            .where(
                and_(
                    PipelineRun.channel_id == channel_id,
                    PipelineRun.updated_at >= today_start,
                )
            )
        )
        return int(result.scalar_one())

    async def count_completed_today(self, db: AsyncSession, channel_id: int) -> int:
        today_start = _utc_today_start()
        result = await db.execute(
            select(func.count())
            .select_from(PipelineRun)
            .where(
                and_(
                    PipelineRun.channel_id == channel_id,
                    PipelineRun.status == PipelineRunStatus.COMPLETED.value,
                    PipelineRun.completed_at.is_not(None),
                    PipelineRun.completed_at >= today_start,
                )
            )
        )
        return int(result.scalar_one())

    async def get_by_id(
        self, db: AsyncSession, run_id: str | UUID
    ) -> PipelineRun | None:
        return await db.get(PipelineRun, _coerce_run_id(run_id))

    async def mark_running(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        *,
        celery_task_id: str | None = None,
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        now = _utcnow()
        run.status = PipelineRunStatus.RUNNING.value
        run.started_at = run.started_at or now
        run.updated_at = now
        if celery_task_id is not None:
            run.celery_task_id = celery_task_id
        await db.flush()
        await db.refresh(run)
        return run

    async def mark_completed(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        *,
        current_step: str | None = None,
        video_metadata_id: int | None = None,
        news_consumption_id: int | None = None,
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        now = _utcnow()
        run.status = PipelineRunStatus.COMPLETED.value
        run.completed_at = now
        run.updated_at = now
        if current_step is not None:
            run.current_step = current_step
        if video_metadata_id is not None:
            run.video_metadata_id = video_metadata_id
        if news_consumption_id is not None:
            run.news_consumption_id = news_consumption_id
        await db.flush()
        await db.refresh(run)
        return run

    async def mark_failed(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        *,
        last_error: str | None = None,
        current_step: str | None = None,
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        now = _utcnow()
        run.status = PipelineRunStatus.FAILED.value
        run.completed_at = now
        run.updated_at = now
        if last_error is not None:
            run.last_error = last_error
        if current_step is not None:
            run.current_step = current_step
        await db.flush()
        await db.refresh(run)
        return run

    async def mark_stale(
        self, db: AsyncSession, run_id: str | UUID
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        now = _utcnow()
        run.status = PipelineRunStatus.STALE.value
        run.updated_at = now
        await db.flush()
        await db.refresh(run)
        return run

    async def update_step(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        current_step: str,
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        run.current_step = current_step
        run.updated_at = _utcnow()
        await db.flush()
        await db.refresh(run)
        return run

    async def increment_retry_count(
        self,
        db: AsyncSession,
        run_id: str | UUID,
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        run.retry_count += 1
        run.updated_at = _utcnow()
        await db.flush()
        await db.refresh(run)
        return run

    async def reset_for_retry(
        self, db: AsyncSession, run_id: str | UUID
    ) -> PipelineRun | None:
        run = await self.get_by_id(db, run_id)
        if not run:
            return None
        run.status = PipelineRunStatus.PENDING.value
        run.updated_at = _utcnow()
        run.celery_task_id = None
        await db.flush()
        await db.refresh(run)
        return run

    async def list_stale_running(self, db: AsyncSession) -> list[PipelineRun]:
        cutoff = _utcnow() - timedelta(minutes=settings.PIPELINE_STALE_AFTER_MINUTES)
        result = await db.execute(
            select(PipelineRun).where(
                and_(
                    PipelineRun.status == PipelineRunStatus.RUNNING.value,
                    PipelineRun.updated_at < cutoff,
                )
            )
        )
        return list(result.scalars().all())

    async def list_retryable_failed(self, db: AsyncSession) -> list[PipelineRun]:
        result = await db.execute(
            select(PipelineRun).where(
                and_(
                    PipelineRun.status == PipelineRunStatus.FAILED.value,
                    PipelineRun.retry_count < settings.PIPELINE_MAX_RETRIES,
                )
            )
        )
        return list(result.scalars().all())

    async def list_retryable_stale(self, db: AsyncSession) -> list[PipelineRun]:
        result = await db.execute(
            select(PipelineRun).where(
                and_(
                    PipelineRun.status == PipelineRunStatus.STALE.value,
                    PipelineRun.retry_count < settings.PIPELINE_MAX_RETRIES,
                )
            )
        )
        return list(result.scalars().all())

    async def list_retryable_for_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        *,
        channel_id: int | None = None,
        limit: int = 100,
    ) -> list[PipelineRun]:
        conditions = [
            Channel.profile_id == profile_id,
            Channel.is_deleted.is_(False),
            PipelineRun.status.in_(
                [
                    PipelineRunStatus.FAILED.value,
                    PipelineRunStatus.STALE.value,
                ]
            ),
            PipelineRun.retry_count < settings.PIPELINE_MAX_RETRIES,
        ]
        if channel_id is not None:
            conditions.append(PipelineRun.channel_id == channel_id)

        result = await db.execute(
            select(PipelineRun)
            .join(Channel, PipelineRun.channel_id == Channel.id)
            .where(and_(*conditions))
            .order_by(PipelineRun.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_for_profile(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        profile_id: int,
    ) -> PipelineRun | None:
        result = await db.execute(
            select(PipelineRun)
            .join(Channel, PipelineRun.channel_id == Channel.id)
            .where(
                and_(
                    PipelineRun.id == _coerce_run_id(run_id),
                    Channel.profile_id == profile_id,
                    Channel.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_exhausted_retries(self, db: AsyncSession) -> list[PipelineRun]:
        result = await db.execute(
            select(PipelineRun).where(
                and_(
                    PipelineRun.status.in_(
                        [
                            PipelineRunStatus.FAILED.value,
                            PipelineRunStatus.STALE.value,
                        ]
                    ),
                    PipelineRun.retry_count >= settings.PIPELINE_MAX_RETRIES,
                )
            )
        )
        return list(result.scalars().all())

    async def list_failed_in_window(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        since: datetime,
        until: datetime,
    ) -> list[PipelineRun]:
        result = await db.execute(
            select(PipelineRun)
            .where(
                and_(
                    PipelineRun.channel_id == channel_id,
                    PipelineRun.status.in_(
                        [
                            PipelineRunStatus.FAILED.value,
                            PipelineRunStatus.STALE.value,
                        ]
                    ),
                    PipelineRun.updated_at >= since,
                    PipelineRun.updated_at < until,
                )
            )
            .order_by(PipelineRun.updated_at.desc())
        )
        return list(result.scalars().all())

    async def list_retryable_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        limit: int = 100,
    ) -> list[PipelineRun]:
        result = await db.execute(
            select(PipelineRun)
            .where(
                and_(
                    PipelineRun.channel_id == channel_id,
                    PipelineRun.status.in_(
                        [
                            PipelineRunStatus.FAILED.value,
                            PipelineRunStatus.STALE.value,
                        ]
                    ),
                    PipelineRun.retry_count < settings.PIPELINE_MAX_RETRIES,
                )
            )
            .order_by(PipelineRun.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
