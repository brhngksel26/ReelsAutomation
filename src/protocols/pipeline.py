from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.pipeline_run import PipelineRun


class PipelineRunRepository(Protocol):
    async def create_run(self, db: AsyncSession, channel_id: int) -> PipelineRun: ...

    async def create_pending_runs(
        self,
        db: AsyncSession,
        channel_id: int,
        count: int,
    ) -> list[str]: ...

    async def list_by_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        limit: int = 20,
    ) -> list[PipelineRun]: ...

    async def count_scheduled_today(self, db: AsyncSession, channel_id: int) -> int: ...

    async def count_completed_today(self, db: AsyncSession, channel_id: int) -> int: ...

    async def get_by_id(
        self, db: AsyncSession, run_id: str | UUID
    ) -> PipelineRun | None: ...

    async def mark_running(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        *,
        celery_task_id: str | None = None,
    ) -> PipelineRun | None: ...

    async def mark_completed(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        *,
        current_step: str | None = None,
        video_metadata_id: int | None = None,
        news_consumption_id: int | None = None,
    ) -> PipelineRun | None: ...

    async def mark_failed(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        *,
        last_error: str | None = None,
        current_step: str | None = None,
    ) -> PipelineRun | None: ...

    async def mark_stale(
        self, db: AsyncSession, run_id: str | UUID
    ) -> PipelineRun | None: ...

    async def update_step(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        current_step: str,
    ) -> PipelineRun | None: ...

    async def increment_retry_count(
        self,
        db: AsyncSession,
        run_id: str | UUID,
    ) -> PipelineRun | None: ...

    async def reset_for_retry(
        self, db: AsyncSession, run_id: str | UUID
    ) -> PipelineRun | None: ...

    async def list_stale_running(self, db: AsyncSession) -> list[PipelineRun]: ...

    async def list_retryable_failed(self, db: AsyncSession) -> list[PipelineRun]: ...

    async def list_retryable_stale(self, db: AsyncSession) -> list[PipelineRun]: ...

    async def list_retryable_for_profile(
        self,
        db: AsyncSession,
        profile_id: int,
        *,
        channel_id: int | None = None,
        limit: int = 100,
    ) -> list[PipelineRun]: ...

    async def get_for_profile(
        self,
        db: AsyncSession,
        run_id: str | UUID,
        profile_id: int,
    ) -> PipelineRun | None: ...

    async def list_exhausted_retries(self, db: AsyncSession) -> list[PipelineRun]: ...

    async def list_failed_in_window(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        since: datetime,
        until: datetime,
    ) -> list[PipelineRun]: ...

    async def list_retryable_for_channel(
        self,
        db: AsyncSession,
        channel_id: int,
        *,
        limit: int = 100,
    ) -> list[PipelineRun]: ...
