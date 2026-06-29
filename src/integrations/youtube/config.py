from __future__ import annotations

from src.schemas.youtube import YouTubeConfig, YouTubeCredentials


def build_youtube_config_from_credentials(
    credentials: dict,
    *,
    request_timeout: float = 120.0,
) -> YouTubeConfig:
    parsed = YouTubeCredentials.model_validate(credentials)
    return YouTubeConfig(credentials=parsed, request_timeout=request_timeout)
