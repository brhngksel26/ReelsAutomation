import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm

from src.core.base_exception import LLMProviderUnavailableError, LLMRateLimitError
from src.core.config import settings
from src.core.enums import LLMProviderType
from src.integrations.llm_manager.config import LLMProviderConfig
from src.integrations.llm_manager.schemas import LLMRequest, LLMResponse, TokenUsage
from src.protocols.llm import BaseLLMProvider

logger = logging.getLogger(__name__)

_MODEL_PREFIX: dict[LLMProviderType, str] = {
    LLMProviderType.OLLAMA: "ollama_chat/",
    LLMProviderType.OPENAI: "openai/",
    LLMProviderType.ANTHROPIC: "anthropic/",
    LLMProviderType.GOOGLE: "gemini/",
}

__all__ = ["BaseLLMProvider", "LiteLLMProvider"]


def _build_model_string(config: LLMProviderConfig) -> str:
    prefix = _MODEL_PREFIX.get(config.provider_type, "")
    return f"{prefix}{config.model_name}"


def _map_usage(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None
    return TokenUsage(
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )


def _translate_litellm_error(exc: Exception) -> Exception:
    error_text = str(exc).lower()
    if "rate limit" in error_text or "429" in error_text:
        return LLMRateLimitError(str(exc))
    return LLMProviderUnavailableError(str(exc))


def resolve_output_max_tokens(explicit: int | None = None) -> int | None:
    """Return None when unlimited output is enabled, otherwise the explicit or default cap."""
    if settings.LLM_UNLIMITED_OUTPUT:
        return None
    if explicit is not None:
        return explicit
    return settings.LLM_MAX_TOKENS


def _resolve_max_tokens(config: LLMProviderConfig, request: LLMRequest) -> int | None:
    if settings.LLM_UNLIMITED_OUTPUT and not request.enforce_max_tokens:
        return None
    if request.max_tokens is not None:
        return request.max_tokens
    return config.max_tokens


def _completion_kwargs(
    config: LLMProviderConfig, request: LLMRequest
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": _build_model_string(config),
        "messages": request.to_messages(),
        "temperature": request.temperature,
        "num_retries": config.max_retries,
        "timeout": config.request_timeout,
    }
    max_tokens = _resolve_max_tokens(config, request)
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if config.api_base:
        kwargs["api_base"] = config.api_base
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if request.response_schema:
        if config.provider_type == LLMProviderType.OLLAMA:
            kwargs["format"] = request.response_schema
        else:
            kwargs["response_format"] = {"type": "json_object"}
    if config.provider_type == LLMProviderType.OLLAMA:
        # Thinking models (e.g. gemma4) otherwise consume the token budget in
        # message.thinking and leave message.content empty for structured JSON.
        kwargs.setdefault("extra_body", {})["think"] = False
    return kwargs


class LiteLLMProvider:
    """Config-driven LiteLLM provider for all supported LLM backends."""

    def __init__(self, config: LLMProviderConfig) -> None:
        self.config = config

    @property
    def provider_name(self) -> str:
        return self.config.provider_type.value

    async def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            response = await litellm.acompletion(
                **_completion_kwargs(self.config, request)
            )
            content = response.choices[0].message.content or ""
            return LLMResponse(
                content=content,
                model=response.model or self.config.model_name,
                provider=self.provider_name,
                usage=_map_usage(response.usage),
            )
        except Exception as exc:
            logger.warning(
                "LLM completion failed for provider=%s: %s", self.provider_name, exc
            )
            raise _translate_litellm_error(exc) from exc

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        try:
            response = await litellm.acompletion(
                **_completion_kwargs(self.config, request),
                stream=True,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            logger.warning(
                "LLM stream failed for provider=%s: %s", self.provider_name, exc
            )
            raise _translate_litellm_error(exc) from exc

    async def health_check(self) -> bool:
        ping_request = LLMRequest(
            user_prompt="ping", max_tokens=5, enforce_max_tokens=True
        )
        try:
            await self.complete(ping_request)
            return True
        except Exception:
            return False
