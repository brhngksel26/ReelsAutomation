from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.config import settings
from src.core.enums import VideoAspect
from src.integrations.llm_manager.schemas import (
    IdeaValidation,
    VideoIdeaOutput,
    VideoScriptOutput,
)
from src.models.channel import Channel
from src.schemas.money_printer_turbo import GenerateVideoParams


class ChannelContext(BaseModel):
    channel_id: int
    name: str
    niche: str
    target_audience: str
    language: str
    tone_of_voice: str
    system_prompt: str
    base_hashtags: list[str]
    estimated_duration_seconds: int = Field(default=45, ge=30, le=50)

    @classmethod
    def from_channel(cls, channel: Channel) -> ChannelContext:
        return cls(
            channel_id=channel.id,
            name=channel.name,
            niche=channel.niche,
            target_audience=channel.target_audience,
            language=channel.language,
            tone_of_voice=channel.tone_of_voice,
            system_prompt=channel.system_prompt,
            base_hashtags=list(channel.base_hashtags or []),
        )


class PipelineVideoContent(BaseModel):
    channel: ChannelContext
    idea: VideoIdeaOutput
    script: VideoScriptOutput | None = None
    validation: IdeaValidation | None = None

    def to_mpt_params(self) -> GenerateVideoParams:
        if self.script is None:
            raise ValueError("script is required to build MoneyPrinterTurbo params")

        voice_name = ""
        if self.channel.language == "en":
            voice_name = settings.MPT_VOICE_NAME_EN

        return GenerateVideoParams(
            video_subject=self.idea.title,
            video_script=self.script.voiceover_text.strip(),
            video_terms=self.idea.suggested_keywords or None,
            video_aspect=VideoAspect.PORTRAIT,
            video_language=self.channel.language,
            voice_name=voice_name,
            custom_system_prompt=self.channel.system_prompt,
            video_script_prompt=self.channel.tone_of_voice,
            paragraph_number=max(len(self.script.script_segments), 1),
            subtitle_enabled=True,
        )


def merge_hashtags(script_hashtags: list[str], base_hashtags: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for tag in [*script_hashtags, *base_hashtags]:
        normalized = tag if tag.startswith("#") else f"#{tag}"
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    return merged
