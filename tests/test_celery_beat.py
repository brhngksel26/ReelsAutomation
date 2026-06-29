from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from src.core.celery_app import celery_app
from src.tasks.health import (
    BEAT_HEARTBEAT_KEY,
    BEAT_STALE_THRESHOLD_SECONDS,
    check_beat_health,
    write_beat_heartbeat,
)


def test_beat_schedule_filename_configured():
    expected = os.getenv("CELERY_BEAT_SCHEDULE_FILENAME", "celerybeat-schedule")
    assert celery_app.conf.beat_schedule_filename == expected


def test_beat_schedule_includes_health_and_retry_tasks():
    schedule = celery_app.conf.beat_schedule
    assert "check-beat-health" in schedule
    assert schedule["check-beat-health"]["task"] == "src.tasks.health.check_beat_health"
    assert schedule["check-beat-health"]["schedule"] == 300.0
    assert "retry-stale-pipelines" in schedule
    assert (
        schedule["retry-stale-pipelines"]["task"]
        == "src.tasks.pipeline.retry_stale_pipelines"
    )
    assert schedule["retry-stale-pipelines"]["schedule"] == 300.0
    assert "retry-failed-publishes" in schedule
    assert (
        schedule["retry-failed-publishes"]["task"]
        == "src.tasks.video.retry_failed_publishes"
    )
    assert "send-daily-channel-digests" in schedule
    assert (
        schedule["send-daily-channel-digests"]["task"]
        == "src.tasks.notifications.send_daily_channel_digests"
    )
    digest_schedule = schedule["send-daily-channel-digests"]["schedule"]
    assert digest_schedule.hour == {20}
    assert digest_schedule.minute == {0}


def test_write_beat_heartbeat_sets_redis_key():
    mock_client = MagicMock()
    with patch("src.tasks.health._redis_client", return_value=mock_client):
        write_beat_heartbeat()
    mock_client.set.assert_called_once()
    args, kwargs = mock_client.set.call_args
    assert args[0] == BEAT_HEARTBEAT_KEY
    assert kwargs["ex"] == BEAT_STALE_THRESHOLD_SECONDS * 2


def test_check_beat_health_alerts_when_heartbeat_missing():
    mock_client = MagicMock()
    mock_client.get.return_value = None
    with (
        patch("src.tasks.health._redis_client", return_value=mock_client),
        patch("src.tasks.health._send_stale_beat_alert") as mock_alert,
    ):
        check_beat_health()
    mock_alert.assert_called_once_with(BEAT_STALE_THRESHOLD_SECONDS)


def test_check_beat_health_alerts_when_heartbeat_stale():
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    mock_client = MagicMock()
    mock_client.get.return_value = stale_time.isoformat()
    with (
        patch("src.tasks.health._redis_client", return_value=mock_client),
        patch("src.tasks.health._send_stale_beat_alert") as mock_alert,
    ):
        check_beat_health()
    mock_alert.assert_called_once()
    assert mock_alert.call_args.args[0] > BEAT_STALE_THRESHOLD_SECONDS


def test_check_beat_health_ok_when_recent():
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=1)
    mock_client = MagicMock()
    mock_client.get.return_value = recent_time.isoformat()
    with (
        patch("src.tasks.health._redis_client", return_value=mock_client),
        patch("src.tasks.health._send_stale_beat_alert") as mock_alert,
    ):
        check_beat_health()
    mock_alert.assert_not_called()
