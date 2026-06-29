from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations import ntfy as ntfy_module
from src.integrations.ntfy import (
    _ascii_header,
    _build_platform_url,
    _format_channel_digest_message,
    _format_pipeline_message,
    _resolve_notification_tag,
    send_channel_daily_digest,
    send_pipeline_notification,
    should_send_pipeline_notification,
)
from src.pipeline.state import PipelineState
from src.schemas.channel_digest import (
    ChannelDigestOut,
    ChannelProfileLink,
    FailedPipelineDigestItem,
    FailedPublishDigestItem,
    PublishedVideoDigestItem,
)


def _sample_state(**overrides) -> PipelineState:
    state: PipelineState = {
        "channel_id": 1,
        "channel_context": {"name": "Chilling Seconds"},
        "video_idea": {
            "title": "The Unseen Observer",
            "hook": "What if something watched you back?",
            "key_points": [],
            "suggested_keywords": [],
            "estimated_duration_seconds": 45,
            "mood": "eerie",
        },
        "video_script": {
            "title": "The Unseen Observer",
            "script_segments": [],
            "voiceover_text": "A" * 50,
            "hashtags": ["horror"],
            "thumbnail_description": "dark hallway",
        },
        "idea_score": 8,
        "video_metadata_id": 7,
        "video_path": "/storage/videos/7.mp4",
        "publish_results": [
            {
                "platform": "youtube_shorts",
                "success": True,
                "platform_video_id": "hC0-BWNmv1U",
            },
        ],
        "current_step": "publish",
        "errors": [],
        "run_id": "run-123",
    }
    state.update(overrides)
    return state


def _mock_http_client(
    *, post_side_effect: object | None = None
) -> tuple[MagicMock, AsyncMock]:
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    if post_side_effect is not None:
        mock_client.post = post_side_effect
    else:
        mock_client.post = AsyncMock(return_value=mock_response)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return mock_cm, mock_client


def test_build_platform_url_youtube_shorts():
    assert (
        _build_platform_url("youtube_shorts", "abc123")
        == "https://youtube.com/shorts/abc123"
    )


def test_ascii_header_replaces_non_ascii_characters():
    assert _ascii_header("Today\u2019s News") == "Today?s News"
    assert _ascii_header("Complete: The Unseen Observer").isascii()


@pytest.mark.asyncio
async def test_send_pipeline_notification_ascii_sanitizes_unicode_title():
    mock_cm, mock_client = _mock_http_client()
    unicode_title = "Today\u2019s Observer"
    state = _sample_state(
        video_idea={
            "title": unicode_title,
            "hook": "What if something watched you back?",
            "key_points": [],
            "suggested_keywords": [],
            "estimated_duration_seconds": 45,
            "mood": "eerie",
        },
        video_script={
            "title": unicode_title,
            "script_segments": [],
            "voiceover_text": "A" * 50,
            "hashtags": ["horror"],
            "thumbnail_description": "dark hallway",
        },
    )

    with (
        patch.object(ntfy_module.settings, "NTFY_ENABLED", True),
        patch.object(ntfy_module.settings, "NTFY_BASE_URL", "http://ntfy.test"),
        patch.object(ntfy_module.settings, "NTFY_TOPIC", "reels-secret"),
        patch("src.integrations.ntfy.httpx.AsyncClient", return_value=mock_cm),
    ):
        await send_pipeline_notification(state)

    _, kwargs = mock_client.post.await_args
    title_header = kwargs["headers"]["Title"]
    assert title_header.isascii()
    assert "\u2019" not in title_header
    assert (
        title_header
        == f"Complete: {unicode_title.encode('ascii', 'replace').decode('ascii')}"
    )
    body = kwargs["content"].decode("utf-8")
    assert unicode_title in body


@pytest.mark.asyncio
async def test_send_pipeline_notification_skipped_when_disabled():
    with (
        patch.object(ntfy_module.settings, "NTFY_ENABLED", False),
        patch.object(ntfy_module.settings, "NTFY_TOPIC", "secret-topic"),
        patch("src.integrations.ntfy.httpx.AsyncClient") as mock_client_cls,
    ):
        await send_pipeline_notification(_sample_state())

    mock_client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_send_pipeline_notification_posts_rich_payload():
    mock_cm, mock_client = _mock_http_client()

    with (
        patch.object(ntfy_module.settings, "NTFY_ENABLED", True),
        patch.object(ntfy_module.settings, "NTFY_BASE_URL", "http://ntfy.test"),
        patch.object(ntfy_module.settings, "NTFY_TOPIC", "reels-secret"),
        patch.object(ntfy_module.settings, "NTFY_REQUEST_TIMEOUT", 5.0),
        patch("src.integrations.ntfy.httpx.AsyncClient", return_value=mock_cm),
    ):
        await send_pipeline_notification(_sample_state())

    mock_client.post.assert_awaited_once()
    args, kwargs = mock_client.post.await_args
    assert args[0] == "http://ntfy.test/reels-secret"
    body = kwargs["content"].decode("utf-8")
    assert "Kanal: Chilling Seconds" in body
    assert "Video: The Unseen Observer" in body
    assert "Fikir skoru: 8/10" in body
    assert "https://youtube.com/shorts/hC0-BWNmv1U" in body
    assert kwargs["headers"]["Title"] == "Complete: The Unseen Observer"
    assert kwargs["headers"]["Tags"] == "white_check_mark"
    assert kwargs["headers"]["Click"] == "https://youtube.com/shorts/hC0-BWNmv1U"
    actions = json.loads(kwargs["headers"]["Actions"])
    assert actions[0]["url"] == "https://youtube.com/shorts/hC0-BWNmv1U"


@pytest.mark.asyncio
async def test_send_pipeline_notification_uses_warning_tag_on_partial_publish():
    mock_cm, mock_client = _mock_http_client()
    state = _sample_state(
        publish_results=[
            {
                "platform": "youtube_shorts",
                "success": True,
                "platform_video_id": "hC0-BWNmv1U",
            },
            {"platform": "tiktok", "success": False, "error": "401 unauthorized"},
        ],
    )

    with (
        patch.object(ntfy_module.settings, "NTFY_ENABLED", True),
        patch.object(ntfy_module.settings, "NTFY_BASE_URL", "http://ntfy.test"),
        patch.object(ntfy_module.settings, "NTFY_TOPIC", "reels-secret"),
        patch("src.integrations.ntfy.httpx.AsyncClient", return_value=mock_cm),
    ):
        await send_pipeline_notification(state)

    _, kwargs = mock_client.post.await_args
    assert kwargs["headers"]["Tags"] == "warning"
    assert kwargs["headers"]["Title"] == "Partial: The Unseen Observer"
    body = _format_pipeline_message(state, pipeline_error=None)
    assert "TikTok: FAIL (401 unauthorized)" in body


@pytest.mark.asyncio
async def test_send_pipeline_notification_swallows_http_errors(caplog):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("server error")
    mock_cm, mock_client = _mock_http_client()
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch.object(ntfy_module.settings, "NTFY_ENABLED", True),
        patch.object(ntfy_module.settings, "NTFY_BASE_URL", "http://ntfy.test"),
        patch.object(ntfy_module.settings, "NTFY_TOPIC", "reels-secret"),
        patch("src.integrations.ntfy.httpx.AsyncClient", return_value=mock_cm),
    ):
        await send_pipeline_notification(_sample_state())

    assert any(
        "ntfy notification failed" in record.message for record in caplog.records
    )


def test_resolve_notification_tag_on_pipeline_error():
    state = _sample_state(current_step="started")
    assert _resolve_notification_tag(state, pipeline_error="boom") == "x"


def test_should_send_pipeline_notification_skips_full_success():
    state = _sample_state()
    assert should_send_pipeline_notification(state, pipeline_error=None) is False


def test_should_send_pipeline_notification_on_pipeline_error():
    state = _sample_state()
    assert should_send_pipeline_notification(state, pipeline_error="boom") is True


def test_should_send_pipeline_notification_on_partial_publish():
    state = _sample_state(
        publish_results=[
            {"platform": "youtube_shorts", "success": False, "error": "limit"}
        ],
    )
    assert should_send_pipeline_notification(state, pipeline_error=None) is True


def test_format_channel_digest_message_includes_counts_and_links():
    digest = ChannelDigestOut(
        channel_id=9,
        channel_name="CelebSpill",
        digest_date=date(2026, 6, 29),
        published=[
            PublishedVideoDigestItem(
                video_id=1,
                hook_text="Hook one",
                platform_type="youtube_shorts",
                platform_label="YouTube Shorts",
                platform_url="https://youtube.com/shorts/abc",
            )
        ],
        failed_publishes=[
            FailedPublishDigestItem(
                video_id=54,
                hook_text="Hook fail",
                platform_type="youtube_shorts",
                platform_label="YouTube Shorts",
                error_log="upload limit exceeded",
            )
        ],
        failed_pipelines=[
            FailedPipelineDigestItem(run_id="run-1", last_error="idea rejected"),
        ],
        retry_pending_publishes=1,
        retry_pending_pipelines=0,
        profile_links=[
            ChannelProfileLink(
                platform_type="youtube_shorts",
                platform_label="YouTube Shorts",
                profile_url="https://youtube.com/@CelebSpill",
            )
        ],
    )
    message = _format_channel_digest_message(digest)
    assert "Günlük özet — CelebSpill" in message
    assert "Yayınlanan: 1 video" in message
    assert "https://youtube.com/shorts/abc" in message
    assert "Video 54" in message
    assert "upload limit exceeded" in message
    assert "Run run-1" in message
    assert "Retry kuyruğu (şu an): 1 publish, 0 pipeline" in message
    assert "https://youtube.com/@CelebSpill" in message


@pytest.mark.asyncio
async def test_send_channel_daily_digest_posts_low_priority_message():
    mock_cm, mock_client = _mock_http_client()
    digest = ChannelDigestOut(
        channel_id=9,
        channel_name="CelebSpill",
        digest_date=date(2026, 6, 29),
        profile_links=[
            ChannelProfileLink(
                platform_type="youtube_shorts",
                platform_label="YouTube Shorts",
                profile_url="https://youtube.com/@CelebSpill",
            )
        ],
    )
    with (
        patch.object(ntfy_module.settings, "NTFY_ENABLED", True),
        patch.object(ntfy_module.settings, "NTFY_BASE_URL", "http://ntfy.test"),
        patch.object(ntfy_module.settings, "NTFY_TOPIC", "reels-secret"),
        patch("src.integrations.ntfy.httpx.AsyncClient", return_value=mock_cm),
    ):
        await send_channel_daily_digest(digest)

    _, kwargs = mock_client.post.await_args
    assert kwargs["headers"]["Title"] == _ascii_header("Günlük özet: CelebSpill")
    assert kwargs["headers"]["Tags"] == "bar_chart"
    assert kwargs["headers"]["Priority"] == "low"
    assert kwargs["headers"]["Click"] == "https://youtube.com/@CelebSpill"
