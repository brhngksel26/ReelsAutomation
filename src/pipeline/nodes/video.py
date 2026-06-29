from __future__ import annotations

import logging
from pathlib import Path

from src.core.database import pipeline_async_session_maker
from src.core.deps import get_video_metadata_crud
from src.core.enums import GenerationStatus
from src.core.unit_of_work import transaction
from src.integrations.llm_manager.schemas import VideoIdeaOutput, VideoScriptOutput
from src.integrations.money_printer_turbo import get_money_printer_client
from src.pipeline.exceptions import PipelineStateError
from src.pipeline.state import PipelineState
from src.schemas.pipeline_contract import ChannelContext, PipelineVideoContent

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path("/storage/videos")


async def produce_video(state: PipelineState) -> dict:
    video_metadata_id = state.get("video_metadata_id")
    idea_payload = state.get("video_idea")
    script_payload = state.get("video_script")
    if video_metadata_id is None or not idea_payload or not script_payload:
        raise PipelineStateError(
            "video_metadata_id, video_idea, and video_script are required before produce_video"
        )

    idea = VideoIdeaOutput.model_validate(idea_payload)
    script = VideoScriptOutput.model_validate(script_payload)
    channel_context_payload = state.get("channel_context")
    if not channel_context_payload:
        raise PipelineStateError("channel_context is required before produce_video")

    channel_context = ChannelContext.model_validate(channel_context_payload)
    content = PipelineVideoContent(channel=channel_context, idea=idea, script=script)
    mpt_params = content.to_mpt_params()

    async with pipeline_async_session_maker() as db:
        async with transaction(db):
            crud = get_video_metadata_crud()
            existing = await crud.get_by_id(db, video_metadata_id)
            if (
                existing
                and existing.generation_status == GenerationStatus.COMPLETED.value
            ):
                video_path = existing.video_path or str(
                    _STORAGE_ROOT / f"{video_metadata_id}.mp4"
                )
                if Path(video_path).exists():
                    logger.info(
                        "produce_video skip idempotent video_metadata_id=%s path=%s",
                        video_metadata_id,
                        video_path,
                    )
                    return {
                        "video_path": video_path,
                        "current_step": "produce_video",
                    }

            await crud.update_generation_status(
                db,
                video_metadata_id,
                GenerationStatus.PROCESSING,
            )

            client = get_money_printer_client()
            task = await client.generate_video(mpt_params)
            completed = await client.wait_for_completion(task.task_id)
            source_path = (completed.videos or completed.combined_videos or [None])[0]
            if not source_path:
                await crud.update_generation_status(
                    db,
                    video_metadata_id,
                    GenerationStatus.FAILED,
                )
                raise PipelineStateError(
                    f"MoneyPrinterTurbo task {task.task_id} completed without a video path"
                )

            destination = _STORAGE_ROOT / f"{video_metadata_id}.mp4"
            destination.parent.mkdir(parents=True, exist_ok=True)
            video_bytes = await client.download_video(source_path)
            destination.write_bytes(video_bytes)
            video_path = str(destination)

            await crud.update_generation_status(
                db,
                video_metadata_id,
                GenerationStatus.COMPLETED,
                video_path=video_path,
            )

    logger.info(
        "produce_video video_metadata_id=%s path=%s",
        video_metadata_id,
        video_path,
    )
    return {
        "video_path": video_path,
        "current_step": "produce_video",
    }
