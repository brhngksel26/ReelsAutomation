from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.core.base_exception import PlatformAuthError, PlatformRequestError
from src.core.http_client import (
    HttpClient,
    translate_http_error,
    translate_request_error,
)
from src.integrations._shared.auth import is_token_expired
from src.schemas.youtube import (
    YouTubeComment,
    YouTubeConfig,
    YouTubeUploadRequest,
    YouTubeUploadResult,
    YouTubeVideoStats,
)

logger = logging.getLogger(__name__)

TOKEN_REFRESH_SKEW_SECONDS = 300


class YouTubeError(Exception):
    pass


class YouTubeRequestError(YouTubeError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class YouTubeAuthError(YouTubeError):
    pass


class YouTubeUploadError(YouTubeError):
    pass


def _default_headers(access_token: str) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }


def _default_client_factory(config: YouTubeConfig) -> Callable[[], HttpClient]:
    def factory() -> HttpClient:
        return HttpClient(
            base_url=config.api_base_url,
            timeout=config.request_timeout,
            headers=_default_headers(config.credentials.access_token),
        )

    return factory


def _to_youtube_error(exc: httpx.HTTPStatusError) -> YouTubeError:
    platform_exc = translate_http_error(exc)
    status_code = exc.response.status_code

    if status_code in {401, 403} or isinstance(platform_exc, PlatformAuthError):
        return YouTubeAuthError(str(platform_exc))
    if isinstance(platform_exc, PlatformRequestError):
        return YouTubeRequestError(
            str(platform_exc), status_code=platform_exc.status_code
        )
    return YouTubeRequestError(str(platform_exc), status_code=status_code)


def _to_youtube_request_error(exc: httpx.RequestError) -> YouTubeRequestError:
    return YouTubeRequestError(str(translate_request_error(exc)))


class YouTubeClient:
    """Async httpx client for YouTube Data API v3."""

    def __init__(
        self,
        config: YouTubeConfig,
        *,
        client_factory: Callable[[], HttpClient] | None = None,
        oauth_client_factory: Callable[[], HttpClient] | None = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory or _default_client_factory(config)
        self._oauth_client_factory = oauth_client_factory or (
            lambda: HttpClient(timeout=config.request_timeout)
        )
        self._on_token_refreshed: (
            Callable[[str, datetime | None], None | Awaitable[None]] | None
        ) = None

    def set_token_refreshed_callback(
        self,
        callback: Callable[[str, datetime | None], None | Awaitable[None]],
    ) -> None:
        self._on_token_refreshed = callback

    def _is_token_expired(self) -> bool:
        return is_token_expired(
            self.config.credentials.token_expires_at,
            skew_seconds=TOKEN_REFRESH_SKEW_SECONDS,
        )

    async def _refresh_access_token(self) -> None:
        credentials = self.config.credentials
        async with self._oauth_client_factory() as client:
            try:
                response = await client.post(
                    self.config.oauth_token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": credentials.refresh_token,
                        "client_id": credentials.client_id,
                        "client_secret": credentials.client_secret,
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise _to_youtube_error(exc) from exc
            except httpx.RequestError as exc:
                raise _to_youtube_request_error(exc) from exc

            payload = response.json()
            access_token = payload.get("access_token")
            if not access_token:
                raise YouTubeAuthError("Token refresh response missing access_token")

            expires_in = payload.get("expires_in")
            token_expires_at = None
            if isinstance(expires_in, int):
                token_expires_at = datetime.now(timezone.utc).timestamp() + expires_in
                token_expires_at = datetime.fromtimestamp(
                    token_expires_at, tz=timezone.utc
                )

            credentials.access_token = access_token
            credentials.token_expires_at = token_expires_at

            if self._on_token_refreshed:
                result = self._on_token_refreshed(access_token, token_expires_at)
                if inspect.iscoroutine(result):
                    await result

    async def _ensure_access_token(self) -> str:
        if self._is_token_expired():
            await self._refresh_access_token()
        return self.config.credentials.access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        absolute_url: str | None = None,
        _auth_retried: bool = False,
    ) -> httpx.Response:
        access_token = await self._ensure_access_token()
        request_headers = _default_headers(access_token)
        if headers:
            request_headers.update(headers)

        async with self._client_factory() as client:
            try:
                if absolute_url:
                    response = await client.request(
                        method,
                        absolute_url,
                        json=json,
                        params=params,
                        headers=request_headers,
                        content=content,
                    )
                else:
                    response = await client.request(
                        method,
                        path,
                        json=json,
                        params=params,
                        headers=request_headers,
                        content=content,
                    )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401 and not _auth_retried:
                    await self._refresh_access_token()
                    return await self._request(
                        method,
                        path,
                        json=json,
                        params=params,
                        headers=headers,
                        content=content,
                        absolute_url=absolute_url,
                        _auth_retried=True,
                    )
                raise _to_youtube_error(exc) from exc
            except httpx.RequestError as exc:
                raise _to_youtube_request_error(exc) from exc

            return response

    async def _init_resumable_upload(self, request: YouTubeUploadRequest) -> str:
        body = {
            "snippet": {
                "title": request.snippet.title,
                "description": request.snippet.description,
                "tags": request.snippet.tags,
                "categoryId": request.snippet.category_id,
            },
            "status": {"privacyStatus": request.privacy_status},
        }
        init_url = (
            f"{self.config.upload_base_url}/videos"
            "?uploadType=resumable&part=snippet,status"
        )
        response = await self._request(
            "POST",
            "",
            json=body,
            headers={"Content-Type": "application/json"},
            absolute_url=init_url,
        )
        location = response.headers.get("Location")
        if not location:
            raise YouTubeUploadError("Resumable upload session missing Location header")
        return location

    async def _upload_video_bytes(
        self, upload_url: str, video_bytes: bytes
    ) -> dict[str, Any]:
        response = await self._request(
            "PUT",
            "",
            content=video_bytes,
            headers={"Content-Type": "video/*"},
            absolute_url=upload_url,
        )
        if not response.content:
            raise YouTubeUploadError("Upload completed without response body")
        payload = response.json()
        if not isinstance(payload, dict):
            raise YouTubeUploadError("Invalid upload response payload")
        return payload

    async def upload_video(self, request: YouTubeUploadRequest) -> YouTubeUploadResult:
        video_path = Path(request.video_path)
        if not video_path.is_file():
            raise YouTubeUploadError(f"Video file not found: {request.video_path}")

        video_bytes = video_path.read_bytes()
        upload_url = await self._init_resumable_upload(request)
        payload = await self._upload_video_bytes(upload_url, video_bytes)

        video_id = payload.get("id")
        if not video_id:
            raise YouTubeUploadError("Upload response missing video id")

        status = None
        status_payload = payload.get("status")
        if isinstance(status_payload, dict):
            status = status_payload.get("uploadStatus")

        return YouTubeUploadResult(video_id=video_id, status=status)

    async def get_video_stats(self, video_id: str) -> YouTubeVideoStats:
        response = await self._request(
            "GET",
            "/videos",
            params={"part": "statistics", "id": video_id},
        )
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []
        if not items:
            raise YouTubeRequestError(f"Video not found: {video_id}", status_code=404)

        statistics = items[0].get("statistics", {})
        return YouTubeVideoStats(
            video_id=video_id,
            view_count=int(statistics.get("viewCount", 0)),
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0)),
        )

    async def list_comments(self, video_id: str) -> list[YouTubeComment]:
        response = await self._request(
            "GET",
            "/commentThreads",
            params={
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 50,
            },
        )
        payload = response.json()
        items = payload.get("items", []) if isinstance(payload, dict) else []

        comments: list[YouTubeComment] = []
        for item in items:
            snippet = (
                item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            )
            comment_id = item.get("snippet", {}).get("topLevelComment", {}).get("id")
            if not comment_id:
                continue
            comments.append(
                YouTubeComment(
                    comment_id=comment_id,
                    text=snippet.get("textDisplay", ""),
                    author=snippet.get("authorDisplayName"),
                    published_at=snippet.get("publishedAt"),
                )
            )
        return comments
