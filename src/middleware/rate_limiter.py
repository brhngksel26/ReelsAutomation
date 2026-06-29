from collections.abc import Callable
from functools import lru_cache

from fastapi import Request
from fastapi.responses import JSONResponse

from src.core.base_exception import RateLimitExceededError
from src.core.config import settings
from src.core.exception_handling_route import ExceptionHandlingRoute
from src.core.rate_limiter import is_allowed

HTTP_RATE_LIMIT_SCOPE = "http"
DEFAULT_RATE_LIMIT_POLICY = (50, 60)
EXACT_RATE_LIMIT_POLICIES: dict[tuple[str, str], tuple[int, int]] = {
    ("POST", "/api/v1/auth/token"): (5, 60),
    ("POST", "/api/v1/auth/register"): (5, 60),
}
PREFIX_RATE_LIMIT_POLICIES: dict[str, tuple[int, int]] = {
    "/api/v1/auth": (20, 60),
    "/api/v1/channels": (50, 60),
    "/api/v1/platforms": (50, 60),
    "/api/v1/videos": (50, 60),
    "/api/v1/users": (50, 60),
}


@lru_cache
def _get_excluded_paths() -> set[str]:
    raw = (settings.RATE_LIMIT_EXCLUDED or "").strip()
    return {path.strip() for path in raw.split(",") if path.strip()}


def _get_exact_overrides() -> dict[tuple[str, str], tuple[int, int]]:
    return EXACT_RATE_LIMIT_POLICIES


def _get_prefix_overrides() -> dict[str, tuple[int, int]]:
    return PREFIX_RATE_LIMIT_POLICIES


def _resolve_policy(*, method: str, path: str) -> tuple[int, int]:
    overrides = _get_exact_overrides()
    if (method, path) in overrides:
        return overrides[(method, path)]
    if ("*", path) in overrides:
        return overrides[("*", path)]

    prefix_overrides = _get_prefix_overrides()
    matching_prefixes = [
        prefix for prefix in prefix_overrides if path.startswith(prefix)
    ]
    if matching_prefixes:
        best_match = max(matching_prefixes, key=len)
        return prefix_overrides[best_match]

    return DEFAULT_RATE_LIMIT_POLICY


def _get_client_identifier(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        forwarded_ip = forwarded_for.split(",", 1)[0].strip()
        if forwarded_ip:
            return forwarded_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


def _build_bucket(request: Request) -> str:
    client_id = _get_client_identifier(request)
    return f"{client_id}|{request.method.upper()}|{request.url.path}"


async def rate_limit_middleware(request: Request, call_next: Callable):
    try:
        path = request.url.path
        api_prefix = settings.RATE_LIMIT_API_PREFIX or "/api/v1/"
        if path in _get_excluded_paths() or not path.startswith(api_prefix):
            return await call_next(request)

        calls, period = _resolve_policy(
            method=request.method.upper(),
            path=path,
        )
        allowed = await is_allowed(
            scope=HTTP_RATE_LIMIT_SCOPE,
            bucket=_build_bucket(request),
            limit=calls,
            window_seconds=period,
        )
        if not allowed:
            raise RateLimitExceededError(
                f"Rate limit exceeded. Maximum {calls} requests per {period} seconds allowed."
            )

        return await call_next(request)
    except RateLimitExceededError as exc:
        return JSONResponse(
            status_code=429,
            content=ExceptionHandlingRoute._error_payload(
                "RATE_LIMIT_EXCEEDED",
                str(exc),
            ),
        )
