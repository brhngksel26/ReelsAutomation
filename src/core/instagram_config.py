from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class InstagramAuthType(str, Enum):
    FACEBOOK_LOGIN = "facebook_login"
    INSTAGRAM_LOGIN = "instagram_login"


class InstagramConfig(BaseModel):
    access_token: str
    ig_user_id: str
    auth_type: InstagramAuthType = InstagramAuthType.FACEBOOK_LOGIN
    api_version: str = "v21.0"
    request_timeout: float = 120.0

    @property
    def graph_base_url(self) -> str:
        host = (
            "graph.instagram.com"
            if self.auth_type == InstagramAuthType.INSTAGRAM_LOGIN
            else "graph.facebook.com"
        )
        return f"https://{host}/{self.api_version}"

    @property
    def rupload_base_url(self) -> str:
        return f"https://rupload.facebook.com/ig-api-upload/{self.api_version}"

    @classmethod
    def from_credentials(cls, credentials: dict[str, Any]) -> InstagramConfig:
        auth_type_raw = credentials.get(
            "auth_type", InstagramAuthType.FACEBOOK_LOGIN.value
        )
        return cls(
            access_token=credentials["access_token"],
            ig_user_id=credentials["ig_user_id"],
            auth_type=InstagramAuthType(auth_type_raw),
        )
