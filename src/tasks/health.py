from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import httpx
import redis
from celery.signals import beat_init

from src.core.celery_app import celery_app
from src.core.config import settings

logger = logging.getLogger(__name__)

BEAT_HEARTBEAT_KEY = "reels:celery_beat:last_heartbeat"
BEAT_HEARTBEAT_INTERVAL_SECONDS = 60
BEAT_STALE_THRESHOLD_SECONDS = 600


def _redis_client() -> redis.Redis | None:
    if not settings.REDIS_ENABLED:
        return None
    try:
        return redis.Redis(
            host=settings.REDIS_HOST,
            port=int(settings.REDIS_PORT),
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
    except Exception:
        logger.warning("Failed to create Redis client for beat health", exc_info=True)
        return None


def write_beat_heartbeat() -> None:
    client = _redis_client()
    if client is None:
        return
    try:
        client.set(
            BEAT_HEARTBEAT_KEY,
            datetime.now(timezone.utc).isoformat(),
            ex=BEAT_STALE_THRESHOLD_SECONDS * 2,
        )
    except Exception:
        logger.warning("Failed to write Celery Beat heartbeat", exc_info=True)


def _heartbeat_loop() -> None:
    while True:
        write_beat_heartbeat()
        time.sleep(BEAT_HEARTBEAT_INTERVAL_SECONDS)


def _start_beat_heartbeat_loop() -> None:
    write_beat_heartbeat()
    thread = threading.Thread(
        target=_heartbeat_loop, daemon=True, name="beat-heartbeat"
    )
    thread.start()


@beat_init.connect
def on_beat_init(**_kwargs) -> None:
    _start_beat_heartbeat_loop()
    logger.info("Celery Beat heartbeat recording started")


def _parse_heartbeat(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Invalid beat heartbeat timestamp: %s", raw)
        return None


def _send_stale_beat_alert(stale_seconds: float) -> None:
    if not (
        settings.NTFY_ENABLED
        and settings.NTFY_BASE_URL.strip()
        and settings.NTFY_TOPIC.strip()
    ):
        return

    title = "Celery Beat unhealthy"
    message = (
        f"Celery Beat heartbeat is stale ({int(stale_seconds)}s). "
        "Periodic tasks may not be running."
    )
    url = f"{settings.NTFY_BASE_URL.rstrip('/')}/{settings.NTFY_TOPIC.strip()}"
    try:
        with httpx.Client(timeout=settings.NTFY_REQUEST_TIMEOUT) as client:
            response = client.post(
                url,
                content=message.encode("utf-8"),
                headers={
                    "Title": title,
                    "Tags": "warning,rotating_light",
                    "Priority": "high",
                },
            )
            response.raise_for_status()
    except Exception:
        logger.warning("Failed to send Celery Beat stale alert via ntfy", exc_info=True)


def _check_beat_health_sync() -> None:
    client = _redis_client()
    if client is None:
        logger.warning("Skipping beat health check: Redis unavailable")
        return

    try:
        last_seen = _parse_heartbeat(client.get(BEAT_HEARTBEAT_KEY))
    except Exception:
        logger.warning("Failed to read Celery Beat heartbeat", exc_info=True)
        return

    if last_seen is None:
        logger.warning("Celery Beat heartbeat missing")
        _send_stale_beat_alert(BEAT_STALE_THRESHOLD_SECONDS)
        return

    stale_seconds = (datetime.now(timezone.utc) - last_seen).total_seconds()
    if stale_seconds > BEAT_STALE_THRESHOLD_SECONDS:
        logger.error(
            "Celery Beat heartbeat stale stale_seconds=%.0f threshold=%s",
            stale_seconds,
            BEAT_STALE_THRESHOLD_SECONDS,
        )
        _send_stale_beat_alert(stale_seconds)
        return

    logger.debug(
        "Celery Beat heartbeat ok stale_seconds=%.0f",
        stale_seconds,
    )


@celery_app.task(name="src.tasks.health.record_beat_heartbeat")
def record_beat_heartbeat() -> None:
    write_beat_heartbeat()


@celery_app.task(name="src.tasks.health.check_beat_health")
def check_beat_health() -> None:
    _check_beat_health_sync()
