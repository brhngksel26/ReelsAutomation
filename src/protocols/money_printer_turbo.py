from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.schemas.money_printer_turbo import (
        AudioParams,
        FileListResult,
        GenerateVideoParams,
        ScriptParams,
        ScriptResult,
        SocialMetadataParams,
        SocialMetadataResult,
        SubtitleParams,
        TaskCreated,
        TaskListResult,
        TaskStatus,
        TermsParams,
        TermsResult,
    )


class MoneyPrinterClient(Protocol):
    async def generate_video(self, params: GenerateVideoParams) -> TaskCreated: ...

    async def generate_subtitle(self, params: SubtitleParams) -> TaskCreated: ...

    async def generate_audio(self, params: AudioParams) -> TaskCreated: ...

    async def get_task(self, task_id: str) -> TaskStatus: ...

    async def list_tasks(
        self, page: int = 1, page_size: int = 10
    ) -> TaskListResult: ...

    async def delete_task(self, task_id: str) -> None: ...

    async def generate_script(self, params: ScriptParams) -> ScriptResult: ...

    async def generate_terms(self, params: TermsParams) -> TermsResult: ...

    async def generate_social_metadata(
        self, params: SocialMetadataParams
    ) -> SocialMetadataResult: ...

    async def wait_for_completion(
        self,
        task_id: str,
        *,
        poll_interval: float | None = None,
        timeout: float | None = None,
    ) -> TaskStatus: ...

    async def download_video(self, file_path: str) -> bytes: ...

    async def list_musics(self) -> FileListResult: ...

    async def list_video_materials(self) -> FileListResult: ...

    async def health_check(self) -> bool: ...
