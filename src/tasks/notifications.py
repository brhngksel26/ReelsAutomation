from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis

from src.core.async_run import run_async
from src.core.celery_app import celery_app
from src.core.database import worker_async_session_maker
from src.core.unit_of_work import transaction
from src.integrations.ntfy import send_channel_daily_digest
from src.services.channel_digest import build_daily_digests_for_active_channels
from src.tasks.health import _redis_client

logger = logging.getLogger(__name__)

DIGEST_SENT_KEY_PREFIX = "reels:digest"
DIGEST_SENT_TTL_SECONDS = 48 * 60 * 60


def _digest_sent_key(channel_id: int, digest_date: str) -> str:
    return f"{DIGEST_SENT_KEY_PREFIX}:{channel_id}:{digest_date}"


def _mark_digest_sent(client: redis.Redis, channel_id: int, digest_date: str) -> bool:
    key = _digest_sent_key(channel_id, digest_date)
    return bool(
        client.set(
            key,
            datetime.now(timezone.utc).isoformat(),
            nx=True,
            ex=DIGEST_SENT_TTL_SECONDS,
        )
    )


async def _send_daily_channel_digests() -> None:
    redis_client = _redis_client()
    now = datetime.now(timezone.utc)
    digest_date = now.date().isoformat()

    async with worker_async_session_maker() as db:
        async with transaction(db):
            digests = await build_daily_digests_for_active_channels(db, now=now)

    sent_count = 0
    skipped_count = 0
    for digest in digests:
        if redis_client is not None:
            if not _mark_digest_sent(redis_client, digest.channel_id, digest_date):
                skipped_count += 1
                logger.info(
                    "Skipping duplicate daily digest channel_id=%s date=%s",
                    digest.channel_id,
                    digest_date,
                )
                continue
        await send_channel_daily_digest(digest)
        sent_count += 1

    logger.info(
        "Daily channel digests processed sent=%s skipped=%s total_channels=%s",
        sent_count,
        skipped_count,
        len(digests),
    )


@celery_app.task(name="src.tasks.notifications.send_daily_channel_digests")
def send_daily_channel_digests() -> None:
    run_async(_send_daily_channel_digests())
