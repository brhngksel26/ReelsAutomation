from __future__ import annotations

from src.core.base_exception import LLMProviderUnavailableError, LLMRateLimitError
from src.core.config import settings
from src.pipeline.exceptions import PipelineChannelNotFoundError, PipelineStateError
from src.tasks.pipeline import retry_stale_pipelines, run_channel_pipeline_task


def test_run_channel_pipeline_task_autoretry_config():
    task = run_channel_pipeline_task

    assert task.acks_late is True
    assert task.__bound__ is True
    assert task.autoretry_for == (
        LLMProviderUnavailableError,
        LLMRateLimitError,
        ConnectionError,
        TimeoutError,
    )
    assert task.dont_autoretry_for == (
        PipelineChannelNotFoundError,
        PipelineStateError,
    )
    assert task.retry_backoff is True
    assert task.retry_backoff_max == settings.PIPELINE_CELERY_RETRY_BACKOFF_MAX
    assert task.max_retries == settings.PIPELINE_CELERY_MAX_RETRIES


def test_retry_stale_pipelines_task_registered():
    assert retry_stale_pipelines.name == "src.tasks.pipeline.retry_stale_pipelines"


def test_retry_stale_pipelines_uses_retry_admin_service():
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_run = MagicMock()
    mock_run.id = "run-1"
    mock_run.channel_id = 9
    mock_run.retry_count = 0

    mock_crud = MagicMock()
    mock_crud.list_stale_running = AsyncMock(return_value=[])
    mock_crud.list_exhausted_retries = AsyncMock(return_value=[])
    mock_crud.list_retryable_stale = AsyncMock(return_value=[])
    mock_crud.list_retryable_failed = AsyncMock(return_value=[mock_run])

    with (
        patch(
            "src.tasks.pipeline.worker_async_session_maker",
        ) as mock_session_maker,
        patch(
            "src.tasks.pipeline.get_pipeline_run_crud",
            return_value=mock_crud,
        ),
        patch(
            "src.services.retry_admin.enqueue_pipeline_retry",
            new_callable=AsyncMock,
            return_value="task-123",
        ) as mock_enqueue,
    ):
        mock_db = AsyncMock()
        mock_begin = MagicMock()
        mock_begin.__aenter__ = AsyncMock(return_value=None)
        mock_begin.__aexit__ = AsyncMock(return_value=None)
        mock_db.begin = MagicMock(return_value=mock_begin)
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        retry_stale_pipelines()

    mock_enqueue.assert_awaited_once()
