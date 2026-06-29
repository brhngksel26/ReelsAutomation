from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.channel import PlatformConfig
from src.models.video import VideoMetadata


@dataclass
class UploadContext:
    video: VideoMetadata
    platform_config: PlatformConfig
    db: AsyncSession | None = None


class PlatformUploader(Protocol):
    async def upload(self, ctx: UploadContext) -> str:
        """Upload video to platform and return platform video ID."""
        ...


UPLOADERS: dict[str, type] = {}


def register_uploader(platform_type: str):
    def decorator(cls):
        UPLOADERS[platform_type] = cls
        return cls

    return decorator


def get_uploader(platform_type: str) -> PlatformUploader:
    uploader_cls = UPLOADERS.get(platform_type)
    if not uploader_cls:
        raise ValueError(f"No uploader registered for platform: {platform_type}")
    return uploader_cls()
