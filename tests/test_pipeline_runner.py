from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.pipeline.runner import _build_thread_id, _initial_state, run_channel_pipeline


def _mock_pipeline_db() -> AsyncMock:
    mock_db = AsyncMock()
    mock_begin = MagicMock()
    mock_begin.__aenter__ = AsyncMock(return_value=None)
    mock_begin.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin = MagicMock(return_value=mock_begin)
    return mock_db


def _mock_session_maker(mock_db: AsyncMock) -> MagicMock:
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_session_maker


def _full_success_result(channel_id: int) -> dict:
    return {
        "current_step": "publish",
        "channel_id": channel_id,
        "video_metadata_id": 42,
        "publish_results": [
            {
                "platform": "youtube_shorts",
                "success": True,
                "platform_video_id": "abc123",
            }
        ],
        "errors": [],
    }


def test_build_thread_id_includes_run_id():
    channel_id = 7
    run_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert _build_thread_id(channel_id, run_id) == f"channel-{channel_id}-{run_id}"


def test_build_thread_id_unique_per_run_id():
    channel_id = 42
    run_a = str(uuid4())
    run_b = str(uuid4())

    thread_a = _build_thread_id(channel_id, run_a)
    thread_b = _build_thread_id(channel_id, run_b)

    assert thread_a != thread_b
    assert run_a in thread_a
    assert run_b in thread_b


def test_initial_state_uses_provided_run_id():
    channel_id = 3
    run_id = str(uuid4())
    state = _initial_state(channel_id, run_id)
    assert state["run_id"] == run_id


def test_initial_state_generates_run_id_when_missing():
    channel_id = 3
    state = _initial_state(channel_id)
    assert state["run_id"]


@pytest.mark.asyncio
async def test_run_channel_pipeline_new_run_invokes_graph():
    run_uuid = uuid4()
    mock_run = MagicMock()
    mock_run.id = run_uuid
    mock_run.channel_id = 5
    mock_run.thread_id = f"channel-5-{run_uuid}"
    mock_run.retry_count = 0

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=_full_success_result(5))
    mock_graph.aget_state = AsyncMock()

    mock_checkpointer = AsyncMock()
    mock_checkpointer.setup = AsyncMock()

    mock_notify = AsyncMock()
    with (
        patch("src.pipeline.runner.get_pipeline_run_crud") as mock_get_crud,
        patch("src.pipeline.runner.build_checkpointer") as mock_build_cp,
        patch("src.pipeline.runner.build_pipeline", return_value=mock_graph),
        patch("src.pipeline.runner.send_pipeline_notification", mock_notify),
        patch("src.pipeline.runner.pipeline_async_session_maker") as mock_session_maker,
    ):
        mock_crud = MagicMock()
        mock_get_crud.return_value = mock_crud
        mock_crud.create_run = AsyncMock(return_value=mock_run)
        mock_crud.mark_running = AsyncMock()
        mock_crud.mark_completed = AsyncMock()

        mock_db = _mock_pipeline_db()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_build_cp.return_value.__aenter__ = AsyncMock(
            return_value=mock_checkpointer
        )
        mock_build_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await run_channel_pipeline(5)

    assert result["current_step"] == "publish"
    mock_crud.create_run.assert_awaited_once()
    mock_crud.mark_running.assert_awaited()
    mock_crud.mark_completed.assert_awaited()
    mock_graph.ainvoke.assert_awaited_once()
    mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_channel_pipeline_resumes_from_checkpoint():
    run_uuid = uuid4()
    run_id = str(run_uuid)
    mock_run = MagicMock()
    mock_run.id = run_uuid
    mock_run.channel_id = 9
    mock_run.thread_id = f"channel-9-{run_uuid}"
    mock_run.retry_count = 1

    checkpoint_state = MagicMock()
    checkpoint_state.values = {"current_step": "script", "channel_id": 9}

    mock_graph = MagicMock()
    mock_graph.aget_state = AsyncMock(return_value=checkpoint_state)
    mock_graph.ainvoke = AsyncMock(return_value=_full_success_result(9))

    mock_checkpointer = AsyncMock()
    mock_checkpointer.setup = AsyncMock()

    mock_notify = AsyncMock()
    with (
        patch("src.pipeline.runner.get_pipeline_run_crud") as mock_get_crud,
        patch("src.pipeline.runner.build_checkpointer") as mock_build_cp,
        patch("src.pipeline.runner.build_pipeline", return_value=mock_graph),
        patch("src.pipeline.runner.send_pipeline_notification", mock_notify),
        patch("src.pipeline.runner.pipeline_async_session_maker") as mock_session_maker,
    ):
        mock_crud = MagicMock()
        mock_get_crud.return_value = mock_crud
        mock_crud.get_by_id = AsyncMock(return_value=mock_run)
        mock_crud.mark_running = AsyncMock()
        mock_crud.update_step = AsyncMock()
        mock_crud.mark_completed = AsyncMock()
        mock_crud.increment_retry_count = AsyncMock()

        mock_db = _mock_pipeline_db()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_build_cp.return_value.__aenter__ = AsyncMock(
            return_value=mock_checkpointer
        )
        mock_build_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await run_channel_pipeline(9, run_id=run_id)

    assert result["current_step"] == "publish"
    mock_graph.aget_state.assert_awaited_once()
    mock_graph.ainvoke.assert_awaited_once()
    assert mock_graph.ainvoke.await_args.args[0] is None
    mock_crud.increment_retry_count.assert_not_awaited()
    mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_channel_pipeline_sends_notification_on_failure():
    run_uuid = uuid4()
    mock_run = MagicMock()
    mock_run.id = run_uuid
    mock_run.channel_id = 5
    mock_run.thread_id = f"channel-5-{run_uuid}"
    mock_run.retry_count = 0

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("pipeline failed"))
    mock_graph.aget_state = AsyncMock()

    mock_checkpointer = AsyncMock()
    mock_checkpointer.setup = AsyncMock()

    mock_notify = AsyncMock()
    with (
        patch("src.pipeline.runner.get_pipeline_run_crud") as mock_get_crud,
        patch("src.pipeline.runner.build_checkpointer") as mock_build_cp,
        patch("src.pipeline.runner.build_pipeline", return_value=mock_graph),
        patch("src.pipeline.runner.send_pipeline_notification", mock_notify),
        patch("src.pipeline.runner.pipeline_async_session_maker") as mock_session_maker,
        patch("src.pipeline.runner.release_consumption", new_callable=AsyncMock),
    ):
        mock_crud = MagicMock()
        mock_get_crud.return_value = mock_crud
        mock_crud.create_run = AsyncMock(return_value=mock_run)
        mock_crud.mark_running = AsyncMock()
        mock_crud.mark_failed = AsyncMock()

        mock_db = _mock_pipeline_db()
        mock_session_maker.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_build_cp.return_value.__aenter__ = AsyncMock(
            return_value=mock_checkpointer
        )
        mock_build_cp.return_value.__aexit__ = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="pipeline failed"):
            await run_channel_pipeline(5)

    mock_notify.assert_awaited_once()
