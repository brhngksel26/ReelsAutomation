from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.base_exception import LLMOutputParseError, LLMProviderUnavailableError
from src.core.enums import LLMProviderType
from src.integrations.llm_manager.config import LLMConfig, LLMProviderConfig
from src.integrations.llm_manager.manager import LLMManager, _parse_json
from src.integrations.llm_manager.prompts.video_idea import build_video_idea_prompt
from src.integrations.llm_manager.prompts.video_script import build_video_script_prompt
from src.integrations.llm_manager.provider import (
    LiteLLMProvider,
    _build_model_string,
    _completion_kwargs,
    resolve_output_max_tokens,
)
from src.integrations.llm_manager.schemas import (
    IdeaValidation,
    LLMRequest,
    LLMResponse,
    VideoIdeaOutput,
)
from src.models.channel import Channel

VALID_IDEA_JSON = """{
  "title": "3 Money Habits",
  "hook": "Stop doing this with your salary",
  "key_points": ["Save first", "Track spending", "Invest early"],
  "suggested_keywords": ["finance", "money"],
  "estimated_duration_seconds": 45,
  "mood": "energetic"
}"""

VALID_SCRIPT_JSON = """{
  "title": "3 Money Habits",
  "script_segments": ["Hook", "Point 1", "CTA"],
  "voiceover_text": "Stop doing this with your salary. Here are three money habits that actually work for young professionals.",
  "hashtags": ["#finance", "#money"],
  "thumbnail_description": "Bold text on dark background"
}"""


@pytest.fixture
def sample_channel() -> Channel:
    return Channel(
        profile_id=1,
        name="Finance Tips",
        niche="Finance",
        target_audience="Young professionals",
        language="en",
        tone_of_voice="motivational",
        system_prompt="Create engaging finance reels",
        base_hashtags=["finance", "money"],
    )


@pytest.fixture
def sample_idea() -> VideoIdeaOutput:
    return VideoIdeaOutput.model_validate_json(VALID_IDEA_JSON)


@pytest.fixture
def ollama_config() -> LLMProviderConfig:
    return LLMProviderConfig(
        provider_type=LLMProviderType.OLLAMA,
        model_name="gemma2:9b",
        api_base="http://localhost:11434",
    )


def test_build_model_string_ollama(ollama_config: LLMProviderConfig):
    assert _build_model_string(ollama_config) == "ollama_chat/gemma2:9b"


def test_build_model_string_openai():
    config = LLMProviderConfig(
        provider_type=LLMProviderType.OPENAI,
        model_name="gpt-4o",
    )
    assert _build_model_string(config) == "openai/gpt-4o"


def test_parse_json_plain():
    result = _parse_json(VALID_IDEA_JSON, VideoIdeaOutput)
    assert result.title == "3 Money Habits"
    assert len(result.key_points) == 3


def test_parse_json_with_fences():
    fenced = f"```json\n{VALID_IDEA_JSON}\n```"
    result = _parse_json(fenced, VideoIdeaOutput)
    assert result.hook == "Stop doing this with your salary"


def test_parse_json_invalid_raises():
    with pytest.raises(LLMOutputParseError):
        _parse_json("not-json", VideoIdeaOutput)


def test_build_video_idea_prompt(sample_channel: Channel):
    system_prompt, user_prompt = build_video_idea_prompt(sample_channel)
    assert "valid JSON only" in system_prompt
    assert "JSON schema" in system_prompt
    assert sample_channel.name in user_prompt
    assert sample_channel.niche in user_prompt
    assert "finance" in user_prompt


def test_build_video_script_prompt(
    sample_channel: Channel, sample_idea: VideoIdeaOutput
):
    system_prompt, user_prompt = build_video_script_prompt(sample_channel, sample_idea)
    assert "valid JSON" in system_prompt
    assert "no wrapper objects" in system_prompt
    assert sample_idea.title in user_prompt
    assert sample_idea.hook in user_prompt
    assert "video_metadata" in user_prompt
    assert "voiceover_text" in user_prompt
    assert "script_segments" in user_prompt


@pytest.mark.asyncio
async def test_litellm_provider_complete_maps_response(
    ollama_config: LLMProviderConfig,
):
    provider = LiteLLMProvider(ollama_config)
    mock_response = SimpleNamespace(
        model="ollama_chat/gemma2:9b",
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    with patch(
        "src.integrations.llm_manager.provider.litellm.acompletion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_completion:
        response = await provider.complete(
            LLMRequest(user_prompt="hello", max_tokens=128)
        )

    assert response.content == '{"ok": true}'
    assert response.provider == "ollama"
    assert response.usage is not None
    assert response.usage.total_tokens == 15
    mock_completion.assert_awaited_once()
    call_kwargs = mock_completion.await_args.kwargs
    assert call_kwargs["model"] == "ollama_chat/gemma2:9b"
    assert call_kwargs["api_base"] == "http://localhost:11434"
    assert call_kwargs["max_tokens"] == 128


def test_completion_kwargs_includes_ollama_format_schema(
    ollama_config: LLMProviderConfig,
):
    schema = IdeaValidation.model_json_schema()
    request = LLMRequest(
        user_prompt="validate",
        response_schema=schema,
        max_tokens=256,
    )
    kwargs = _completion_kwargs(ollama_config, request)
    assert kwargs["format"] == schema
    assert kwargs["max_tokens"] == 256


def test_completion_kwargs_omits_max_tokens_when_unlimited(
    ollama_config: LLMProviderConfig,
):
    with patch("src.integrations.llm_manager.provider.settings") as mock_settings:
        mock_settings.LLM_UNLIMITED_OUTPUT = True
        kwargs = _completion_kwargs(ollama_config, LLMRequest(user_prompt="hello"))
    assert "max_tokens" not in kwargs


def test_completion_kwargs_omits_max_tokens_when_unlimited_even_with_explicit_cap(
    ollama_config: LLMProviderConfig,
):
    with patch("src.integrations.llm_manager.provider.settings") as mock_settings:
        mock_settings.LLM_UNLIMITED_OUTPUT = True
        kwargs = _completion_kwargs(
            ollama_config,
            LLMRequest(user_prompt="hello", max_tokens=512),
        )
    assert "max_tokens" not in kwargs


def test_completion_kwargs_honors_enforce_max_tokens_when_unlimited(
    ollama_config: LLMProviderConfig,
):
    with patch("src.integrations.llm_manager.provider.settings") as mock_settings:
        mock_settings.LLM_UNLIMITED_OUTPUT = True
        kwargs = _completion_kwargs(
            ollama_config,
            LLMRequest(user_prompt="ping", max_tokens=5, enforce_max_tokens=True),
        )
    assert kwargs["max_tokens"] == 5


def test_completion_kwargs_disables_ollama_thinking(ollama_config: LLMProviderConfig):
    kwargs = _completion_kwargs(ollama_config, LLMRequest(user_prompt="hello"))
    assert kwargs["extra_body"]["think"] is False


def test_resolve_output_max_tokens_returns_none_when_unlimited():
    with patch("src.integrations.llm_manager.provider.settings") as mock_settings:
        mock_settings.LLM_UNLIMITED_OUTPUT = True
        assert resolve_output_max_tokens(512) is None
        assert resolve_output_max_tokens() is None


def test_resolve_output_max_tokens_returns_explicit_when_limited():
    with patch("src.integrations.llm_manager.provider.settings") as mock_settings:
        mock_settings.LLM_UNLIMITED_OUTPUT = False
        mock_settings.LLM_MAX_TOKENS = 8192
        assert resolve_output_max_tokens(1024) == 1024
        assert resolve_output_max_tokens() == 8192


@pytest.mark.asyncio
async def test_manager_complete_structured_passes_schema(
    ollama_config: LLMProviderConfig,
):
    config = LLMConfig(default_provider=ollama_config)
    manager = LLMManager(config)
    captured_request: LLMRequest | None = None

    async def _capture(request: LLMRequest) -> LLMResponse:
        nonlocal captured_request
        captured_request = request
        return LLMResponse(
            content='{"score": 8, "is_acceptable": true, "reason": "Strong hook."}',
            model="gemma2:9b",
            provider="ollama",
        )

    with patch.object(manager, "_complete_with_fallback", side_effect=_capture):
        result = await manager.complete_structured(
            system_prompt="sys",
            user_prompt="user",
            response_model=IdeaValidation,
            max_tokens=1024,
        )

    assert result.score == 8
    assert captured_request is not None
    assert captured_request.response_schema == IdeaValidation.model_json_schema()
    assert captured_request.max_tokens == 1024


def test_parse_json_truncated_raises():
    truncated = '{"score": 8, "is_acceptable": true, "reason": "Incomplete'
    with pytest.raises(LLMOutputParseError):
        _parse_json(truncated, IdeaValidation)


@pytest.mark.asyncio
async def test_litellm_provider_translates_errors(ollama_config: LLMProviderConfig):
    provider = LiteLLMProvider(ollama_config)

    with patch(
        "src.integrations.llm_manager.provider.litellm.acompletion",
        new_callable=AsyncMock,
        side_effect=Exception("connection refused"),
    ):
        with pytest.raises(LLMProviderUnavailableError):
            await provider.complete(LLMRequest(user_prompt="hello"))


@pytest.mark.asyncio
async def test_manager_generate_video_idea_uses_unlimited_tokens_when_enabled(
    sample_channel: Channel,
):
    config = LLMConfig(default_provider=LLMProviderConfig())
    manager = LLMManager(config)
    mock_response = LLMResponse(
        content=VALID_IDEA_JSON,
        model="gemma2:9b",
        provider="ollama",
    )
    captured_request: LLMRequest | None = None

    async def _capture(request: LLMRequest) -> LLMResponse:
        nonlocal captured_request
        captured_request = request
        return mock_response

    with (
        patch("src.integrations.llm_manager.provider.settings") as mock_settings,
        patch.object(manager, "_complete_with_fallback", side_effect=_capture),
    ):
        mock_settings.LLM_UNLIMITED_OUTPUT = True
        mock_settings.LLM_MAX_TOKENS = 8192
        mock_settings.LLM_SCRIPT_MAX_TOKENS = 8192
        idea = await manager.generate_video_idea(sample_channel)

    assert idea.title == "3 Money Habits"
    assert captured_request is not None
    assert captured_request.max_tokens is None


@pytest.mark.asyncio
async def test_manager_generate_video_script(
    sample_channel: Channel, sample_idea: VideoIdeaOutput
):
    config = LLMConfig(default_provider=LLMProviderConfig())
    manager = LLMManager(config)
    mock_response = LLMResponse(
        content=VALID_SCRIPT_JSON,
        model="gemma2:9b",
        provider="ollama",
    )

    with patch.object(
        manager,
        "_complete_with_fallback",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        script = await manager.generate_video_script(sample_channel, sample_idea)

    assert script.voiceover_text.startswith("Stop doing this")
    assert "#finance" in script.hashtags


@pytest.mark.asyncio
async def test_manager_fallback_on_primary_failure():
    primary = LLMProviderConfig(
        provider_type=LLMProviderType.OLLAMA, model_name="primary"
    )
    fallback = LLMProviderConfig(
        provider_type=LLMProviderType.OPENAI, model_name="fallback"
    )
    config = LLMConfig(default_provider=primary, fallback_providers=[fallback])
    manager = LLMManager(config)

    primary_provider = MagicMock()
    primary_provider.provider_name = "ollama"
    primary_provider.complete = AsyncMock(
        side_effect=LLMProviderUnavailableError("down")
    )

    fallback_provider = MagicMock()
    fallback_provider.provider_name = "openai"
    fallback_provider.complete = AsyncMock(
        return_value=LLMResponse(
            content=VALID_IDEA_JSON, model="fallback", provider="openai"
        )
    )

    manager._provider = primary_provider
    manager._fallbacks = [fallback_provider]

    response = await manager._complete_with_fallback(LLMRequest(user_prompt="test"))
    assert response.provider == "openai"
    primary_provider.complete.assert_awaited_once()
    fallback_provider.complete.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires running Ollama instance")
async def test_ollama_integration_health_check():
    manager = LLMManager(LLMConfig())
    result = await manager.health_check()
    assert result["status"] == "healthy"
