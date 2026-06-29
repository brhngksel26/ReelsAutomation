from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from src.core.base_exception import (
    PlatformAuthError,
    PlatformError,
    PlatformRateLimitError,
    PlatformRequestError,
)
from src.core.config import settings

logger = logging.getLogger(__name__)

RETRYABLE_STATUS_CODES = frozenset({500, 502, 503, 504})


def translate_http_error(exc: httpx.HTTPStatusError) -> PlatformError:
    status_code = exc.response.status_code
    try:
        payload = exc.response.json()
        message = (
            (
                payload.get("error", {}).get("message")
                if isinstance(payload.get("error"), dict)
                else None
            )
            or payload.get("message")
            or payload.get("detail")
            or str(exc)
        )
    except Exception:
        message = str(exc)

    if status_code == 401:
        return PlatformAuthError(message)
    if status_code == 429:
        retry_after: float | None = None
        header = exc.response.headers.get("retry-after")
        if header:
            try:
                retry_after = float(header)
            except ValueError:
                retry_after = None
        return PlatformRateLimitError(message, retry_after=retry_after)

    return PlatformRequestError(message, status_code=status_code)


def translate_request_error(exc: httpx.RequestError) -> PlatformRequestError:
    return PlatformRequestError(f"Platform request failed: {exc}")


async def request_with_retry(
    request_fn: Callable[[], Awaitable[httpx.Response]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_status_codes: frozenset[int] = RETRYABLE_STATUS_CODES,
) -> httpx.Response:
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = await request_fn()
            if response.status_code in retryable_status_codes and attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Retryable HTTP %s; retrying in %.1fs (attempt %d/%d)",
                    response.status_code,
                    delay,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code in retryable_status_codes
                and attempt < max_retries
            ):
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Retryable HTTP %s; retrying in %.1fs (attempt %d/%d)",
                    exc.response.status_code,
                    delay,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)
                last_exc = exc
                continue
            raise translate_http_error(exc) from exc
        except httpx.RequestError as exc:
            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "Request error; retrying in %.1fs (attempt %d/%d): %s",
                    delay,
                    attempt + 1,
                    max_retries,
                    exc,
                )
                await asyncio.sleep(delay)
                last_exc = exc
                continue
            raise translate_request_error(exc) from exc

    if last_exc:
        if isinstance(last_exc, httpx.HTTPStatusError):
            raise translate_http_error(last_exc) from last_exc
        raise translate_request_error(last_exc) from last_exc

    raise PlatformRequestError("Request failed after retries")


def _default_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.HTTP_CONNECT_TIMEOUT,
        read=settings.HTTP_READ_TIMEOUT,
        write=settings.HTTP_WRITE_TIMEOUT,
        pool=settings.HTTP_POOL_TIMEOUT,
    )


def _default_limits() -> httpx.Limits:
    return httpx.Limits(
        max_connections=settings.HTTP_MAX_CONNECTIONS,
        max_keepalive_connections=settings.HTTP_MAX_KEEPALIVE,
    )


class HttpClient(httpx.AsyncClient):
    def __init__(
        self,
        base_url: str = "",
        *,
        timeout: float | httpx.Timeout | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        default_headers = headers or {}
        resolved_timeout: float | httpx.Timeout
        if timeout is None:
            resolved_timeout = _default_timeout()
        elif isinstance(timeout, (int, float)):
            resolved_timeout = float(timeout)
        else:
            resolved_timeout = timeout

        client_kwargs: dict[str, Any] = {
            "base_url": base_url,
            "timeout": resolved_timeout,
            "headers": default_headers,
            "limits": kwargs.pop("limits", _default_limits()),
            "follow_redirects": kwargs.pop("follow_redirects", True),
        }
        if "http2" not in kwargs:
            client_kwargs["http2"] = settings.HTTP_HTTP2_ENABLED

        super().__init__(**client_kwargs, **kwargs)

    async def get(
        self,
        url: str = "",
        *,
        params: dict | None = None,
        headers: dict | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return await super().get(url, params=params, headers=headers, **kwargs)

    async def post(
        self,
        url: str = "",
        *,
        json: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return await super().post(url, json=json, data=data, headers=headers, **kwargs)

    async def put(
        self,
        url: str = "",
        *,
        json: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return await super().put(url, json=json, data=data, headers=headers, **kwargs)

    async def patch(
        self,
        url: str = "",
        *,
        json: dict | None = None,
        data: dict | None = None,
        headers: dict | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return await super().patch(url, json=json, data=data, headers=headers, **kwargs)

    async def delete(
        self,
        url: str = "",
        *,
        headers: dict | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        return await super().delete(url, headers=headers, **kwargs)
