from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

from src.core.base_exception import (
    MoneyPrinterRequestError,
    MoneyPrinterTaskError,
    MoneyPrinterTimeoutError,
)
from src.core.config import settings
from src.core.http_client import HttpClient
from src.schemas.money_printer_turbo import (
    AudioParams,
    FileListResult,
    GenerateVideoParams,
    MoneyPrinterConfig,
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

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


def build_money_printer_config_from_settings() -> MoneyPrinterConfig:
    return MoneyPrinterConfig(
        base_url=settings.MPT_BASE_URL,
        api_token=settings.MPT_API_TOKEN,
        request_timeout=settings.MPT_REQUEST_TIMEOUT,
        poll_interval=settings.MPT_POLL_INTERVAL,
        poll_timeout=settings.MPT_POLL_TIMEOUT,
    )


def _default_headers(config: MoneyPrinterConfig) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if config.api_token:
        headers["Authorization"] = f"Bearer {config.api_token}"
    return headers


def _default_client_factory(config: MoneyPrinterConfig) -> Callable[[], HttpClient]:
    def factory() -> HttpClient:
        return HttpClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.request_timeout,
            headers=_default_headers(config),
        )

    return factory


def _translate_http_error(exc: httpx.HTTPStatusError) -> MoneyPrinterRequestError:
    status_code = exc.response.status_code
    try:
        payload = exc.response.json()
        message = payload.get("message") or payload.get("detail") or str(exc)
    except Exception:
        message = str(exc)
    return MoneyPrinterRequestError(message, status_code=status_code)


def _translate_request_error(exc: httpx.RequestError) -> MoneyPrinterRequestError:
    return MoneyPrinterRequestError(f"MoneyPrinterTurbo request failed: {exc}")


def _normalize_download_path(file_path: str) -> str:
    normalized = unquote(file_path.strip())
    if normalized.startswith(("http://", "https://")):
        normalized = urlparse(normalized).path

    normalized = normalized.lstrip("/")
    if normalized.startswith("api/v1/download/"):
        normalized = normalized.removeprefix("api/v1/download/")
    if normalized.startswith("tasks/"):
        normalized = normalized.removeprefix("tasks/")
    return normalized


class MoneyPrinterTurboClient:
    """Async client for MoneyPrinterTurbo /api/v1 endpoints."""

    def __init__(
        self,
        config: MoneyPrinterConfig,
        *,
        client_factory: Callable[[], HttpClient] | None = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory or _default_client_factory(config)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        async with self._client_factory() as client:
            try:
                response = await client.request(method, path, json=json, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise _translate_http_error(exc) from exc
            except httpx.RequestError as exc:
                raise _translate_request_error(exc) from exc

            if not response.content:
                return None

            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return response.content

            return response.json()

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        if not isinstance(payload, dict):
            raise MoneyPrinterRequestError("Invalid MoneyPrinterTurbo response payload")

        status = payload.get("status")
        if status != 200:
            message = payload.get("message") or "MoneyPrinterTurbo request failed"
            raise MoneyPrinterRequestError(message, status_code=status)

        return payload.get("data")

    async def generate_video(self, params: GenerateVideoParams) -> TaskCreated:
        data = self._unwrap(
            await self._request(
                "POST",
                f"{API_PREFIX}/videos",
                json=params.model_dump(mode="json", exclude_none=True),
            )
        )
        return TaskCreated.model_validate(data)

    async def generate_subtitle(self, params: SubtitleParams) -> TaskCreated:
        data = self._unwrap(
            await self._request(
                "POST",
                f"{API_PREFIX}/subtitle",
                json=params.model_dump(mode="json", exclude_none=True),
            )
        )
        return TaskCreated.model_validate(data)

    async def generate_audio(self, params: AudioParams) -> TaskCreated:
        data = self._unwrap(
            await self._request(
                "POST",
                f"{API_PREFIX}/audio",
                json=params.model_dump(mode="json", exclude_none=True),
            )
        )
        return TaskCreated.model_validate(data)

    async def get_task(self, task_id: str) -> TaskStatus:
        data = self._unwrap(await self._request("GET", f"{API_PREFIX}/tasks/{task_id}"))
        return TaskStatus.model_validate(data)

    async def list_tasks(self, page: int = 1, page_size: int = 10) -> TaskListResult:
        data = self._unwrap(
            await self._request(
                "GET",
                f"{API_PREFIX}/tasks",
                params={"page": page, "page_size": page_size},
            )
        )
        return TaskListResult.model_validate(data)

    async def delete_task(self, task_id: str) -> None:
        self._unwrap(await self._request("DELETE", f"{API_PREFIX}/tasks/{task_id}"))

    async def generate_script(self, params: ScriptParams) -> ScriptResult:
        data = self._unwrap(
            await self._request(
                "POST",
                f"{API_PREFIX}/scripts",
                json=params.model_dump(mode="json", exclude_none=True),
            )
        )
        return ScriptResult.model_validate(data)

    async def generate_terms(self, params: TermsParams) -> TermsResult:
        data = self._unwrap(
            await self._request(
                "POST",
                f"{API_PREFIX}/terms",
                json=params.model_dump(mode="json", exclude_none=True),
            )
        )
        return TermsResult.model_validate(data)

    async def generate_social_metadata(
        self, params: SocialMetadataParams
    ) -> SocialMetadataResult:
        data = self._unwrap(
            await self._request(
                "POST",
                f"{API_PREFIX}/social-metadata",
                json=params.model_dump(mode="json", exclude_none=True),
            )
        )
        return SocialMetadataResult.model_validate(data)

    async def list_musics(self) -> FileListResult:
        data = self._unwrap(await self._request("GET", f"{API_PREFIX}/musics"))
        return FileListResult.model_validate(data)

    async def list_video_materials(self) -> FileListResult:
        data = self._unwrap(await self._request("GET", f"{API_PREFIX}/video_materials"))
        return FileListResult.model_validate(data)

    async def wait_for_completion(
        self,
        task_id: str,
        *,
        poll_interval: float | None = None,
        timeout: float | None = None,
    ) -> TaskStatus:
        interval = (
            poll_interval if poll_interval is not None else self.config.poll_interval
        )
        max_wait = timeout if timeout is not None else self.config.poll_timeout
        deadline = time.monotonic() + max_wait

        while True:
            task = await self.get_task(task_id)

            if task.is_complete:
                return task

            if task.is_failed:
                raise MoneyPrinterTaskError(
                    f"MoneyPrinterTurbo task {task_id} failed",
                    task_id=task_id,
                )

            if time.monotonic() >= deadline:
                raise MoneyPrinterTimeoutError(
                    f"MoneyPrinterTurbo task {task_id} timed out after {max_wait}s",
                    task_id=task_id,
                )

            await asyncio.sleep(interval)

    async def download_video(self, file_path: str) -> bytes:
        normalized_path = _normalize_download_path(file_path)
        content = await self._request("GET", f"{API_PREFIX}/download/{normalized_path}")
        if not isinstance(content, bytes):
            raise MoneyPrinterRequestError(
                "Expected binary video content from download endpoint"
            )
        return content

    async def health_check(self) -> bool:
        try:
            await self.list_musics()
            return True
        except Exception:
            return False


@lru_cache
def get_money_printer_client() -> MoneyPrinterTurboClient:
    return MoneyPrinterTurboClient(build_money_printer_config_from_settings())
