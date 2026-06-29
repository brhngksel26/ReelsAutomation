import json
import logging
import re
import time
from functools import lru_cache
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.core.base_exception import LLMError, LLMOutputParseError
from src.core.config import settings
from src.integrations.llm_manager.config import LLMConfig, LLMProviderConfig
from src.integrations.llm_manager.prompts.video_idea import build_video_idea_prompt
from src.integrations.llm_manager.prompts.video_script import build_video_script_prompt
from src.integrations.llm_manager.provider import (
    LiteLLMProvider,
    resolve_output_max_tokens,
)
from src.integrations.llm_manager.schemas import (
    LLMRequest,
    LLMResponse,
    VideoIdeaOutput,
    VideoScriptOutput,
)
from src.models.channel import Channel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE_PATTERN = re.compile(
    r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE
)


def build_llm_config_from_settings() -> LLMConfig:
    return LLMConfig(
        default_provider=LLMProviderConfig(
            provider_type=settings.LLM_PROVIDER,
            model_name=settings.LLM_MODEL_NAME,
            api_base=settings.LLM_API_BASE,
            api_key=settings.LLM_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            request_timeout=settings.LLM_REQUEST_TIMEOUT,
            max_retries=settings.LLM_MAX_RETRIES,
        )
    )


def _create_provider(config: LLMProviderConfig) -> LiteLLMProvider:
    return LiteLLMProvider(config)


def _strip_json_fences(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = _JSON_FENCE_PATTERN.sub("", stripped).strip()
    return stripped


def _parse_json(content: str, model_cls: type[T]) -> T:
    cleaned = _strip_json_fences(content)
    try:
        return model_cls.model_validate_json(cleaned)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise LLMOutputParseError(
            f"Failed to parse LLM output as {model_cls.__name__}: {exc}"
        ) from exc


class LLMManager:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._provider = _create_provider(config.default_provider)
        self._fallbacks = [
            _create_provider(provider_config)
            for provider_config in config.fallback_providers
        ]

    async def complete(
        self,
        *,
        system_prompt: str | None,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> T:
        return await self.complete_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def complete_structured(
        self,
        *,
        system_prompt: str | None,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> T:
        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_schema=response_model.model_json_schema(),
        )
        response = await self._complete_with_fallback(request)
        return _parse_json(response.content, response_model)

    async def _complete_with_fallback(self, request: LLMRequest) -> LLMResponse:
        providers = [self._provider, *self._fallbacks]
        last_error: Exception | None = None

        for provider in providers:
            started_at = time.perf_counter()
            try:
                response = await provider.complete(request)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                logger.info(
                    "llm_completion_success provider=%s model=%s latency_ms=%s tokens=%s",
                    provider.provider_name,
                    response.model,
                    latency_ms,
                    response.usage.model_dump() if response.usage else None,
                )
                return response
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm_provider_failed provider=%s error=%s",
                    provider.provider_name,
                    exc,
                )

        if last_error is None:
            raise LLMError("No LLM providers configured")
        raise last_error

    async def generate_video_idea(
        self,
        channel: Channel,
        recent_context: list[dict] | None = None,
        news_item: dict | None = None,
    ) -> VideoIdeaOutput:
        system_prompt, user_prompt = build_video_idea_prompt(
            channel,
            recent_context,
            news_item=news_item,
        )
        return await self.complete_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=VideoIdeaOutput,
            temperature=0.8,
            max_tokens=resolve_output_max_tokens(),
        )

    async def generate_video_script(
        self,
        channel: Channel,
        idea: VideoIdeaOutput,
    ) -> VideoScriptOutput:
        system_prompt, user_prompt = build_video_script_prompt(channel, idea)
        return await self.complete_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=VideoScriptOutput,
            temperature=0.7,
            max_tokens=resolve_output_max_tokens(settings.LLM_SCRIPT_MAX_TOKENS),
        )

    async def health_check(self) -> dict[str, str]:
        is_healthy = await self._provider.health_check()
        return {
            "provider": self._provider.provider_name,
            "model": self.config.default_provider.model_name,
            "status": "healthy" if is_healthy else "unhealthy",
        }


@lru_cache
def get_llm_manager() -> LLMManager:
    return LLMManager(build_llm_config_from_settings())
