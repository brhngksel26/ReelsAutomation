from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.core.config import TikTokConfig
from src.core.http_client import HttpClient
from src.schemas.tiktok import (
    TikTokFileSourceInfo,
    TikTokInitResponse,
    TikTokPostInfo,
    TikTokStatusResponse,
    TikTokUploadResult,
    TikTokUrlSourceInfo,
    TikTokVideoListResult,
    TikTokVideoQueryResult,
)

DIRECT_POST_INIT_PATH = "/v2/post/publish/video/init/"
INBOX_UPLOAD_INIT_PATH = "/v2/post/publish/inbox/video/init/"
PUBLISH_STATUS_PATH = "/v2/post/publish/status/fetch/"
VIDEO_LIST_PATH = "/v2/video/list/"
VIDEO_QUERY_PATH = "/v2/video/query/"

DEFAULT_VIDEO_FIELDS = (
    "id,title,cover_image_url,create_time,video_description,"
    "duration,height,width,share_url,like_count,comment_count,share_count,view_count"
)


class TikTokError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
    ):
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class TikTokRequestError(TikTokError):
    pass


class TikTokUploadError(TikTokError):
    pass


class TikTokTimeoutError(TikTokError):
    def __init__(self, message: str, *, publish_id: str | None = None):
        self.publish_id = publish_id
        super().__init__(message)


def _default_headers(config: TikTokConfig) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {config.access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def _default_client_factory(config: TikTokConfig) -> Callable[[], HttpClient]:
    def factory() -> HttpClient:
        return HttpClient(
            base_url=config.base_url.rstrip("/"),
            timeout=config.request_timeout,
            headers=_default_headers(config),
            http2=False,
        )

    return factory


def _default_upload_client_factory(
    config: TikTokConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Callable[[], HttpClient]:
    def factory() -> HttpClient:
        return HttpClient(
            timeout=config.request_timeout,
            http2=False,
            transport=transport,
        )

    return factory


def _translate_http_error(exc: httpx.HTTPStatusError) -> TikTokRequestError:
    status_code = exc.response.status_code
    error_code: str | None = None
    message = str(exc)
    try:
        payload = exc.response.json()
        error = payload.get("error") or {}
        error_code = error.get("code")
        message = error.get("message") or message
    except Exception:
        pass
    return TikTokRequestError(message, status_code=status_code, error_code=error_code)


def _translate_request_error(exc: httpx.RequestError) -> TikTokRequestError:
    return TikTokRequestError(f"TikTok request failed: {exc}")


class TikTokClient:
    """Async TikTok Content Posting + Display API client."""

    def __init__(
        self,
        config: TikTokConfig,
        *,
        client_factory: Callable[[], HttpClient] | None = None,
        upload_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory or _default_client_factory(config)
        self._upload_client_factory = _default_upload_client_factory(
            config,
            transport=upload_transport,
        )

    @staticmethod
    def _unwrap(payload: Any) -> Any:
        if not isinstance(payload, dict):
            raise TikTokRequestError("Invalid TikTok response payload")

        error = payload.get("error") or {}
        error_code = error.get("code")
        if error_code and error_code != "ok":
            message = error.get("message") or "TikTok request failed"
            raise TikTokRequestError(message, error_code=error_code)

        return payload.get("data")

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

    async def init_direct_post(
        self,
        post_info: TikTokPostInfo,
        source_info: TikTokFileSourceInfo | TikTokUrlSourceInfo,
    ) -> TikTokInitResponse:
        body = {
            "post_info": post_info.model_dump(mode="json", exclude_none=True),
            "source_info": source_info.model_dump(mode="json", exclude_none=True),
        }
        data = self._unwrap(
            await self._request("POST", DIRECT_POST_INIT_PATH, json=body)
        )
        return TikTokInitResponse.model_validate(data)

    async def init_inbox_upload(
        self,
        source_info: TikTokFileSourceInfo | TikTokUrlSourceInfo,
    ) -> TikTokInitResponse:
        body = {"source_info": source_info.model_dump(mode="json", exclude_none=True)}
        data = self._unwrap(
            await self._request("POST", INBOX_UPLOAD_INIT_PATH, json=body)
        )
        return TikTokInitResponse.model_validate(data)

    async def upload_video_file(
        self,
        upload_url: str,
        video_bytes: bytes,
        *,
        content_type: str = "video/mp4",
    ) -> None:
        total_size = len(video_bytes)
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(total_size),
            "Content-Range": f"bytes 0-{total_size - 1}/{total_size}",
        }
        async with self._upload_client_factory() as client:
            try:
                response = await client.put(
                    upload_url,
                    content=video_bytes,
                    headers=headers,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise _translate_http_error(exc) from exc
            except httpx.RequestError as exc:
                raise _translate_request_error(exc) from exc

    async def fetch_publish_status(self, publish_id: str) -> TikTokStatusResponse:
        data = self._unwrap(
            await self._request(
                "POST", PUBLISH_STATUS_PATH, json={"publish_id": publish_id}
            )
        )
        return TikTokStatusResponse.model_validate(data)

    async def wait_for_publish(
        self,
        publish_id: str,
        *,
        poll_interval: float | None = None,
        timeout: float | None = None,
    ) -> TikTokStatusResponse:
        interval = (
            poll_interval if poll_interval is not None else self.config.poll_interval
        )
        max_wait = timeout if timeout is not None else self.config.poll_timeout
        deadline = time.monotonic() + max_wait

        while True:
            status = await self.fetch_publish_status(publish_id)

            if status.is_terminal:
                if not status.is_success:
                    reason = status.fail_reason or "unknown"
                    raise TikTokUploadError(
                        f"TikTok publish {publish_id} failed: {reason}",
                        error_code=reason,
                    )
                return status

            if time.monotonic() >= deadline:
                raise TikTokTimeoutError(
                    f"TikTok publish {publish_id} timed out after {max_wait}s",
                    publish_id=publish_id,
                )

            await asyncio.sleep(interval)

    async def upload_direct_post(
        self,
        *,
        post_info: TikTokPostInfo,
        source_info: TikTokFileSourceInfo | TikTokUrlSourceInfo,
        video_bytes: bytes | None = None,
    ) -> TikTokUploadResult:
        init = await self.init_direct_post(post_info, source_info)
        if init.upload_url:
            if video_bytes is None:
                raise TikTokUploadError(
                    "video_bytes required for FILE_UPLOAD direct post"
                )
            await self.upload_video_file(init.upload_url, video_bytes)

        status = await self.wait_for_publish(init.publish_id)
        post_id = (
            status.publicly_available_post_id[0]
            if status.publicly_available_post_id
            else None
        )
        return TikTokUploadResult(publish_id=init.publish_id, platform_video_id=post_id)

    async def upload_inbox(
        self,
        *,
        source_info: TikTokFileSourceInfo | TikTokUrlSourceInfo,
        video_bytes: bytes | None = None,
    ) -> TikTokUploadResult:
        init = await self.init_inbox_upload(source_info)
        if init.upload_url:
            if video_bytes is None:
                raise TikTokUploadError(
                    "video_bytes required for FILE_UPLOAD inbox upload"
                )
            await self.upload_video_file(init.upload_url, video_bytes)

        status = await self.wait_for_publish(init.publish_id)
        post_id = (
            status.publicly_available_post_id[0]
            if status.publicly_available_post_id
            else None
        )
        return TikTokUploadResult(publish_id=init.publish_id, platform_video_id=post_id)

    async def list_videos(
        self,
        *,
        fields: str = DEFAULT_VIDEO_FIELDS,
        cursor: int | None = None,
        max_count: int = 20,
    ) -> TikTokVideoListResult:
        body: dict[str, Any] = {"max_count": max_count}
        if cursor is not None:
            body["cursor"] = cursor
        data = self._unwrap(
            await self._request(
                "POST", VIDEO_LIST_PATH, json=body, params={"fields": fields}
            )
        )
        return TikTokVideoListResult.model_validate(data)

    async def query_videos(
        self,
        video_ids: list[str],
        *,
        fields: str = DEFAULT_VIDEO_FIELDS,
    ) -> TikTokVideoQueryResult:
        if not video_ids:
            return TikTokVideoQueryResult()
        data = self._unwrap(
            await self._request(
                "POST",
                VIDEO_QUERY_PATH,
                json={"filters": {"video_ids": video_ids}},
                params={"fields": fields},
            )
        )
        return TikTokVideoQueryResult.model_validate(data)
