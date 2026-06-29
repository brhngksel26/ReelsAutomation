from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx

from src.core.http_client import HttpClient
from src.core.instagram_config import InstagramAuthType, InstagramConfig
from src.schemas.instagram import (
    InstagramAuthError,
    InstagramComment,
    InstagramCommentsResult,
    InstagramInsight,
    InstagramInsightsResult,
    InstagramRequestError,
    InstagramUploadError,
    MediaContainerResult,
    MediaPublishResult,
    ReelsPublishParams,
    ResumableUploadSession,
)

logger = logging.getLogger(__name__)

DEFAULT_INSIGHT_METRICS = "reach,plays,likes,comments,shares,saved,total_interactions"


def _default_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _default_client_factory(config: InstagramConfig) -> Callable[[], HttpClient]:
    def factory() -> HttpClient:
        return HttpClient(
            base_url=config.graph_base_url,
            timeout=config.request_timeout,
            headers=_default_headers(),
        )

    return factory


def _default_rupload_client_factory(
    config: InstagramConfig,
) -> Callable[[], HttpClient]:
    def factory() -> HttpClient:
        return HttpClient(
            base_url=config.rupload_base_url,
            timeout=config.request_timeout,
            headers=_default_headers(),
        )

    return factory


def _extract_error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message") or error.get("error_user_msg") or fallback
        message = payload.get("message")
        if isinstance(message, str):
            return message
    return fallback


def _extract_error_code(payload: Any) -> int | None:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            if isinstance(code, int):
                return code
    return None


def _translate_http_error(exc: httpx.HTTPStatusError) -> InstagramRequestError:
    status_code = exc.response.status_code
    try:
        payload = exc.response.json()
    except Exception:
        payload = None

    message = _extract_error_message(payload, str(exc))
    error_code = _extract_error_code(payload)

    if status_code in {401, 403}:
        return InstagramAuthError(
            message, status_code=status_code, error_code=error_code
        )
    if status_code == 429:
        return InstagramRequestError(
            message, status_code=status_code, error_code=error_code
        )
    return InstagramRequestError(
        message, status_code=status_code, error_code=error_code
    )


def _translate_request_error(exc: httpx.RequestError) -> InstagramRequestError:
    return InstagramRequestError(f"Instagram API request failed: {exc}")


class InstagramClient:
    """Async client for Instagram Graph content publishing and analytics."""

    def __init__(
        self,
        config: InstagramConfig,
        *,
        client_factory: Callable[[], HttpClient] | None = None,
        rupload_client_factory: Callable[[], HttpClient] | None = None,
    ) -> None:
        self.config = config
        self._client_factory = client_factory or _default_client_factory(config)
        self._rupload_client_factory = (
            rupload_client_factory or _default_rupload_client_factory(config)
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        client_factory: Callable[[], HttpClient] | None = None,
    ) -> Any:
        request_params = dict(params or {})
        request_params.setdefault("access_token", self.config.access_token)

        factory = client_factory or self._client_factory
        async with factory() as client:
            try:
                response = await client.request(
                    method,
                    path,
                    params=request_params,
                    data=data,
                    json=json,
                )
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

    async def create_media_container(
        self,
        params: ReelsPublishParams,
        *,
        ig_user_id: str | None = None,
    ) -> MediaContainerResult:
        owner_id = ig_user_id or self.config.ig_user_id
        payload = params.model_dump(mode="json", exclude_none=True)

        result = await self._request(
            "POST",
            f"/{owner_id}/media",
            data=payload,
        )

        if not isinstance(result, dict) or "id" not in result:
            raise InstagramUploadError(
                "Invalid media container response from Instagram API"
            )

        return MediaContainerResult.model_validate(result)

    async def publish_media(
        self,
        creation_id: str,
        *,
        ig_user_id: str | None = None,
    ) -> MediaPublishResult:
        owner_id = ig_user_id or self.config.ig_user_id
        result = await self._request(
            "POST",
            f"/{owner_id}/media_publish",
            data={"creation_id": creation_id},
        )

        if not isinstance(result, dict) or "id" not in result:
            raise InstagramUploadError(
                "Invalid media publish response from Instagram API"
            )

        return MediaPublishResult.model_validate(result)

    async def publish_reels(
        self,
        *,
        video_url: str,
        caption: str = "",
        media_type: str = "REELS",
        ig_user_id: str | None = None,
        share_to_feed: bool | None = None,
    ) -> str:
        container = await self.create_media_container(
            ReelsPublishParams(
                video_url=video_url,
                caption=caption,
                media_type=media_type,
                share_to_feed=share_to_feed,
            ),
            ig_user_id=ig_user_id,
        )
        published = await self.publish_media(container.id, ig_user_id=ig_user_id)
        return published.id

    async def init_resumable_upload(
        self,
        *,
        file_size: int,
        mime_type: str = "video/mp4",
        ig_user_id: str | None = None,
    ) -> ResumableUploadSession:
        """Skeleton: initialize resumable upload via rupload.facebook.com (facebook_login only)."""
        if self.config.auth_type != InstagramAuthType.FACEBOOK_LOGIN:
            raise InstagramUploadError(
                "Resumable upload is only supported with facebook_login auth type"
            )

        owner_id = ig_user_id or self.config.ig_user_id
        upload_path = f"/{owner_id}"

        async with self._rupload_client_factory() as client:
            try:
                response = await client.post(
                    upload_path,
                    headers={
                        "Authorization": f"OAuth {self.config.access_token}",
                        "offset": "0",
                        "file_size": str(file_size),
                        "Content-Type": mime_type,
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise _translate_http_error(exc) from exc
            except httpx.RequestError as exc:
                raise _translate_request_error(exc) from exc

        upload_url = f"{self.config.rupload_base_url.rstrip('/')}/{owner_id}"
        return ResumableUploadSession(
            ig_user_id=owner_id,
            upload_url=upload_url,
            file_size=file_size,
            mime_type=mime_type,
        )

    async def upload_resumable_chunk(
        self,
        session: ResumableUploadSession,
        chunk: bytes,
        *,
        offset: int,
    ) -> None:
        """Skeleton: upload a chunk to rupload.facebook.com."""
        if self.config.auth_type != InstagramAuthType.FACEBOOK_LOGIN:
            raise InstagramUploadError(
                "Resumable upload is only supported with facebook_login auth type"
            )

        async with self._rupload_client_factory() as client:
            try:
                response = await client.post(
                    f"/{session.ig_user_id}",
                    content=chunk,
                    headers={
                        "Authorization": f"OAuth {self.config.access_token}",
                        "offset": str(offset),
                        "Content-Type": session.mime_type,
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise _translate_http_error(exc) from exc
            except httpx.RequestError as exc:
                raise _translate_request_error(exc) from exc

    async def finalize_resumable_upload(
        self,
        session: ResumableUploadSession,
        *,
        caption: str = "",
        media_type: str = "REELS",
    ) -> MediaContainerResult:
        """Skeleton: finalize resumable upload and create media container."""
        raise NotImplementedError(
            "Resumable upload finalize is not yet implemented; use publish_reels with a public URL"
        )

    async def get_insights(
        self,
        media_id: str,
        *,
        metrics: str = DEFAULT_INSIGHT_METRICS,
    ) -> InstagramInsightsResult:
        """Fetch media insights (skeleton-ready Graph API wrapper)."""
        result = await self._request(
            "GET",
            f"/{media_id}/insights",
            params={"metric": metrics},
        )

        if not isinstance(result, dict):
            raise InstagramRequestError("Invalid insights response from Instagram API")

        raw_insights = result.get("data", [])
        insights = [
            InstagramInsight.model_validate(item)
            for item in raw_insights
            if isinstance(item, dict)
        ]
        return InstagramInsightsResult(media_id=media_id, insights=insights)

    async def list_comments(
        self,
        media_id: str,
        *,
        limit: int = 25,
    ) -> InstagramCommentsResult:
        """List comments on a media object (skeleton-ready Graph API wrapper)."""
        result = await self._request(
            "GET",
            f"/{media_id}/comments",
            params={"fields": "id,text,username,timestamp", "limit": limit},
        )

        if not isinstance(result, dict):
            raise InstagramRequestError("Invalid comments response from Instagram API")

        raw_comments = result.get("data", [])
        comments = [
            InstagramComment.model_validate(item)
            for item in raw_comments
            if isinstance(item, dict)
        ]
        return InstagramCommentsResult(media_id=media_id, comments=comments)
