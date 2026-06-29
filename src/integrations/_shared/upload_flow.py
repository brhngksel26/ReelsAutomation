from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.schemas.platform_models import UploadResult


@dataclass
class UploadContext:
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    platform_settings: dict[str, Any] = field(default_factory=dict)
    credentials: dict[str, Any] = field(default_factory=dict)


@dataclass
class UploadSession:
    session_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseUploadFlow(ABC):
    async def execute(self, ctx: UploadContext) -> UploadResult:
        credentials = await self.authenticate(ctx)
        ctx.credentials = credentials
        await self.validate_media(ctx)
        session = await self.init_upload(ctx, credentials)
        await self.transfer_media(ctx, session)
        result = await self.finalize(ctx, session)
        return await self.poll_until_ready(ctx, result)

    @abstractmethod
    async def authenticate(self, ctx: UploadContext) -> dict[str, Any]: ...

    async def validate_media(self, ctx: UploadContext) -> None:
        return None

    @abstractmethod
    async def init_upload(
        self, ctx: UploadContext, credentials: dict[str, Any]
    ) -> UploadSession: ...

    @abstractmethod
    async def transfer_media(
        self, ctx: UploadContext, session: UploadSession
    ) -> None: ...

    @abstractmethod
    async def finalize(
        self, ctx: UploadContext, session: UploadSession
    ) -> UploadResult: ...

    async def poll_until_ready(
        self, ctx: UploadContext, result: UploadResult
    ) -> UploadResult:
        return result
