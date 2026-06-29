from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import PlatformStatus, PlatformType


class PlatformConnectIn(BaseModel):
    channel_id: int
    platform_type: PlatformType
    credentials_json: dict = Field(default_factory=dict)
    platform_specific_settings: dict = Field(default_factory=dict)


class PlatformStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    platform_type: PlatformType
    status: PlatformStatus
    platform_specific_settings: dict
