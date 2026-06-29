import pytest

from src.core.enums import VideoAspect
from src.integrations.llm_manager.schemas import (
    IdeaValidation,
    VideoIdeaOutput,
    VideoScriptOutput,
)
from src.models.channel import Channel
from src.schemas.pipeline_contract import (
    ChannelContext,
    PipelineVideoContent,
    merge_hashtags,
)


@pytest.fixture
def eternal_seconds_channel() -> Channel:
    return Channel(
        id=1,
        profile_id=1,
        name="Eternal Seconds",
        niche="Psychology & Philosophy",
        target_audience="Curious adults seeking meaning",
        language="en",
        tone_of_voice="thoughtful and cinematic",
        system_prompt="Create introspective short videos about human behavior and philosophy.",
        base_hashtags=["eternalseconds", "philosophy", "psychology"],
    )


@pytest.fixture
def sample_idea() -> VideoIdeaOutput:
    return VideoIdeaOutput(
        title="Why We Fear Silence",
        hook="Your brain treats silence like danger.",
        key_points=["Evolutionary wiring", "Modern overstimulation", "Practical reset"],
        suggested_keywords=["silence", "psychology", "mindfulness"],
        estimated_duration_seconds=45,
        mood="reflective",
    )


@pytest.fixture
def sample_script() -> VideoScriptOutput:
    return VideoScriptOutput(
        title="Why We Fear Silence",
        script_segments=["Hook", "Point 1", "Point 2", "CTA"],
        voiceover_text=(
            "Your brain treats silence like danger. In a world of constant noise, "
            "stillness feels unfamiliar. Here is why that happens and how to reset."
        ),
        hashtags=["#psychology", "#silence"],
        thumbnail_description="Person sitting alone in dim light",
    )


def test_channel_context_from_channel(eternal_seconds_channel: Channel):
    context = ChannelContext.from_channel(eternal_seconds_channel)
    assert context.channel_id == 1
    assert context.name == "Eternal Seconds"
    assert context.language == "en"
    assert "philosophy" in context.base_hashtags


def test_pipeline_video_content_to_mpt_params(
    eternal_seconds_channel: Channel,
    sample_idea: VideoIdeaOutput,
    sample_script: VideoScriptOutput,
):
    content = PipelineVideoContent(
        channel=ChannelContext.from_channel(eternal_seconds_channel),
        idea=sample_idea,
        script=sample_script,
        validation=IdeaValidation(score=8, is_acceptable=True, reason="Strong fit."),
    )
    params = content.to_mpt_params()

    assert params.video_subject == sample_idea.title
    assert params.video_script == sample_script.voiceover_text
    assert params.video_terms == sample_idea.suggested_keywords
    assert params.video_language == "en"
    assert params.voice_name == "en-US-AriaNeural"
    assert params.custom_system_prompt == eternal_seconds_channel.system_prompt
    assert params.video_script_prompt == eternal_seconds_channel.tone_of_voice
    assert params.video_aspect == VideoAspect.PORTRAIT
    assert params.subtitle_enabled is True
    assert params.paragraph_number == 4


def test_merge_hashtags_dedupes_and_normalizes():
    merged = merge_hashtags(
        ["psychology", "#Philosophy"],
        ["#philosophy", "eternalseconds"],
    )
    assert merged == ["#psychology", "#Philosophy", "#eternalseconds"]


def test_to_mpt_params_requires_script(
    eternal_seconds_channel: Channel, sample_idea: VideoIdeaOutput
):
    content = PipelineVideoContent(
        channel=ChannelContext.from_channel(eternal_seconds_channel),
        idea=sample_idea,
    )
    with pytest.raises(ValueError, match="script is required"):
        content.to_mpt_params()
