from pydantic import BaseModel, Field

from src.core.enums import LLMProviderType


class LLMProviderConfig(BaseModel):
    provider_type: LLMProviderType = LLMProviderType.OLLAMA
    model_name: str = "gemma4:12b"
    api_base: str = "http://localhost:11434"
    api_key: str | None = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2048, ge=1)
    request_timeout: int = 60
    max_retries: int = 3


class LLMConfig(BaseModel):
    default_provider: LLMProviderConfig = LLMProviderConfig()
    fallback_providers: list[LLMProviderConfig] = []
