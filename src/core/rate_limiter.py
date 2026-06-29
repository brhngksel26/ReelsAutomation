import logging
import time

import redis.asyncio as aioredis

from src.core.base_exception import (
    RedisClientCreationError,
)
from src.core.config import settings
from src.core.database import redis_pool

logger = logging.getLogger(__name__)

KEY_PREFIX = "rate_limit"
_redis_warning_logged = False
_redis_failure_warning_logged = False


def _log_redis_unavailable_once() -> None:
    global _redis_warning_logged
    if _redis_warning_logged:
        return

    logger.warning("Redis not available, skipping rate limit")
    _redis_warning_logged = True


def _log_redis_failure_once(exc: Exception) -> None:
    global _redis_failure_warning_logged
    if _redis_failure_warning_logged:
        return

    logger.warning("Redis rate limiter unavailable, bypassing limit checks: %s", exc)
    _redis_failure_warning_logged = True


def _validate_rate_limit(limit: int, window_seconds: int) -> None:
    if limit <= 0:
        raise ValueError("Rate limit calls must be greater than zero")
    if window_seconds <= 0:
        raise ValueError("Rate limit period must be greater than zero")


def _build_key(*, scope: str, bucket: str) -> str:
    return f"{KEY_PREFIX}:{scope}:{bucket}"


async def _get_redis_client() -> aioredis.Redis | None:
    if not settings.REDIS_ENABLED or not redis_pool:
        _log_redis_unavailable_once()
        return None

    try:
        return aioredis.Redis(connection_pool=redis_pool)
    except Exception as exc:
        raise RedisClientCreationError(f"Redis client creation failed: {exc}") from exc


async def _reserve_slot(
    redis: aioredis.Redis,
    *,
    key: str,
    window_seconds: int,
) -> tuple[int, float]:
    now = time.time()
    cutoff = now - window_seconds

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff)
    pipe.zcard(key)
    results = await pipe.execute()
    count = int(results[1])

    if count < 0:
        count = 0

    return count, now


async def _add_hit(
    redis: aioredis.Redis,
    *,
    key: str,
    window_seconds: int,
    now: float,
) -> None:
    member = f"{now}:{time.time_ns()}"
    await redis.zadd(key, {member: now})
    await redis.expire(key, window_seconds + 60)


async def _get_oldest_score(redis: aioredis.Redis, *, key: str) -> float | None:
    oldest = await redis.zrange(key, 0, 0, withscores=True)
    if not oldest:
        return None
    return float(oldest[0][1])


async def is_allowed(
    *,
    scope: str,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> bool:
    _validate_rate_limit(limit, window_seconds)

    redis = await _get_redis_client()
    if not redis:
        return True

    try:
        key = _build_key(scope=scope, bucket=bucket)
        count, now = await _reserve_slot(
            redis,
            key=key,
            window_seconds=window_seconds,
        )
        if count >= limit:
            return False

        await _add_hit(
            redis,
            key=key,
            window_seconds=window_seconds,
            now=now,
        )
        return True
    except Exception as exc:
        _log_redis_failure_once(exc)
        return True
