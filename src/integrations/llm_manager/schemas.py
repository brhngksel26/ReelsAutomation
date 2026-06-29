from typing import Any

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    system_prompt: str | None = None
    user_prompt: str
    temperature: float = 0.7
    max_tokens: int | None = None
    enforce_max_tokens: bool = False
    response_schema: dict[str, Any] | None = None

    def to_messages(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": self.user_prompt})
        return messages


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: TokenUsage | None = None


class VideoIdeaOutput(BaseModel):
    title: str
    hook: str
    key_points: list[str]
    suggested_keywords: list[str]
    estimated_duration_seconds: int = Field(ge=30, le=50)
    mood: str


class VideoScriptOutput(BaseModel):
    title: str
    script_segments: list[str]
    voiceover_text: str = Field(min_length=50, max_length=2000)
    hashtags: list[str]
    thumbnail_description: str


class IdeaValidation(BaseModel):
    score: int = Field(ge=1, le=10)
    is_acceptable: bool
    reason: str = Field(max_length=200)
