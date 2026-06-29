from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ValidationError

from src.core.enums import PlatformType


class YouTubeCredentials(BaseModel):
    access_token: str
    refresh_token: str
    token_expires_at: datetime
    client_id: str
    client_secret: str


class TikTokCredentials(BaseModel):
    access_token: str
    refresh_token: str
    open_id: str
    token_expires_at: datetime


InstagramAuthType = Literal["facebook_login", "instagram_login"]


class InstagramCredentials(BaseModel):
    access_token: str
    token_expires_at: datetime
    ig_user_id: str
    auth_type: InstagramAuthType = "facebook_login"


PlatformCredentials = YouTubeCredentials | TikTokCredentials | InstagramCredentials

_CREDENTIAL_MODELS: dict[PlatformType, type[BaseModel]] = {
    PlatformType.YOUTUBE_SHORTS: YouTubeCredentials,
    PlatformType.TIKTOK: TikTokCredentials,
    PlatformType.INSTAGRAM: InstagramCredentials,
}


def parse_credentials(
    platform_type: PlatformType | str,
    data: dict,
) -> PlatformCredentials:
    if isinstance(platform_type, str):
        platform_type = PlatformType(platform_type)

    model_cls = _CREDENTIAL_MODELS.get(platform_type)
    if model_cls is None:
        raise ValueError(f"Unsupported platform type: {platform_type}")

    return model_cls.model_validate(data)


def validate_credentials_json(
    platform_type: PlatformType | str,
    data: dict,
) -> dict:
    """Validate and return normalized credentials_json for storage."""
    try:
        credentials = parse_credentials(platform_type, data)
    except ValidationError as exc:
        raise ValueError(f"Invalid credentials for {platform_type}: {exc}") from exc
    return credentials.model_dump(mode="json")
