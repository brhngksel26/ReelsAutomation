from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.integrations.llm_manager.schemas import LLMRequest, LLMResponse


class BaseLLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def complete(self, request: LLMRequest) -> LLMResponse: ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]: ...

    async def health_check(self) -> bool: ...
