from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from src.core.http_client import HttpClient
from src.integrations.youtube.client import (
    YouTubeAuthError,
    YouTubeClient,
    YouTubeRequestError,
    YouTubeUploadError,
)
from src.integrations.youtube.config import build_youtube_config_from_credentials
from src.schemas.youtube import (
    YouTubePlatformSettings,
    YouTubeUploadRequest,
    YouTubeVideoSnippet,
)

try:
    from src.core.config import YouTubeConfig, YouTubeCredentials
except ImportError:  # pragma: no cover - legacy import path during refactor
    from src.schemas.youtube import YouTubeConfig, YouTubeCredentials

from src.services.uploaders.base import UploadContext
from src.services.uploaders.youtube import YouTubeShortsUploader, _build_snippet


def _credentials(**overrides) -> YouTubeCredentials:
    base = {
        "access_token": "ya29.test-token",
        "refresh_token": "1//refresh",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "token_expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    base.update(overrides)
    return YouTubeCredentials.model_validate(base)


def _config(**credential_overrides) -> YouTubeConfig:
    credentials = _credentials(**credential_overrides)
    return build_youtube_config_from_credentials(credentials.model_dump())


def _make_client(
    handlers: dict[str, Callable[[httpx.Request], httpx.Response]],
    *,
    config: YouTubeConfig | None = None,
) -> YouTubeClient:
    resolved_config = config or _config()

    def handler(request: httpx.Request) -> httpx.Response:
        route_key = f"{request.method} {request.url.path}"
        query = request.url.query
        if isinstance(query, bytes):
            query = query.decode()
        full_key = f"{route_key}?{query}" if query else route_key

        if full_key in handlers:
            return handlers[full_key](request)
        if route_key in handlers:
            return handlers[route_key](request)

        absolute_key = f"{request.method} {request.url}"
        if absolute_key in handlers:
            return handlers[absolute_key](request)

        return httpx.Response(
            404, json={"error": {"message": f"not found: {full_key}"}}
        )

    transport = httpx.MockTransport(handler)

    def http_client_factory() -> HttpClient:
        return HttpClient(
            transport=transport,
            http2=False,
            timeout=resolved_config.request_timeout,
        )

    def api_client_factory() -> HttpClient:
        return HttpClient(
            base_url=resolved_config.api_base_url,
            transport=transport,
            http2=False,
            timeout=resolved_config.request_timeout,
            headers={
                "Authorization": f"Bearer {resolved_config.credentials.access_token}"
            },
        )

    return YouTubeClient(
        resolved_config,
        client_factory=api_client_factory,
        oauth_client_factory=http_client_factory,
    )


@pytest.mark.asyncio
async def test_upload_video_resumable_flow(tmp_path: Path):
    video_file = tmp_path / "short.mp4"
    video_file.write_bytes(b"fake-video-content")

    upload_calls: list[httpx.Request] = []

    def init_upload(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["snippet"]["title"] == "Test Hook"
        assert body["status"]["privacyStatus"] == "private"
        return httpx.Response(
            200,
            headers={"Location": "https://upload.example.com/resumable/abc"},
        )

    def put_upload(request: httpx.Request) -> httpx.Response:
        upload_calls.append(request)
        assert request.content == b"fake-video-content"
        return httpx.Response(
            200,
            json={
                "id": "yt-video-123",
                "status": {"uploadStatus": "uploaded"},
            },
        )

    client = _make_client(
        {
            "POST /upload/youtube/v3/videos": init_upload,
            "PUT https://upload.example.com/resumable/abc": put_upload,
        }
    )

    result = await client.upload_video(
        YouTubeUploadRequest(
            snippet=YouTubeVideoSnippet(
                title="Test Hook",
                description="Caption body",
                tags=["Shorts", "finance"],
                category_id="22",
            ),
            privacy_status="private",
            video_path=str(video_file),
        )
    )

    assert result.video_id == "yt-video-123"
    assert result.status == "uploaded"
    assert len(upload_calls) == 1


@pytest.mark.asyncio
async def test_upload_video_missing_file():
    client = _make_client({})

    with pytest.raises(YouTubeUploadError, match="Video file not found"):
        await client.upload_video(
            YouTubeUploadRequest(
                snippet=YouTubeVideoSnippet(title="T", description="D"),
                video_path="/does/not/exist.mp4",
            )
        )


@pytest.mark.asyncio
async def test_get_video_stats():
    client = _make_client(
        {
            "GET /youtube/v3/videos?part=statistics&id=yt-video-123": lambda _: httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "yt-video-123",
                            "statistics": {
                                "viewCount": "1500",
                                "likeCount": "120",
                                "commentCount": "45",
                            },
                        }
                    ]
                },
            )
        }
    )

    stats = await client.get_video_stats("yt-video-123")

    assert stats.video_id == "yt-video-123"
    assert stats.view_count == 1500
    assert stats.like_count == 120
    assert stats.comment_count == 45


@pytest.mark.asyncio
async def test_list_comments():
    client = _make_client(
        {
            "GET /youtube/v3/commentThreads?part=snippet&videoId=yt-video-123&maxResults=50": lambda _: httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {
                                "topLevelComment": {
                                    "id": "comment-1",
                                    "snippet": {
                                        "textDisplay": "Great short!",
                                        "authorDisplayName": "Viewer",
                                        "publishedAt": "2026-01-01T00:00:00Z",
                                    },
                                }
                            }
                        }
                    ]
                },
            )
        }
    )

    comments = await client.list_comments("yt-video-123")

    assert len(comments) == 1
    assert comments[0].comment_id == "comment-1"
    assert comments[0].text == "Great short!"
    assert comments[0].author == "Viewer"


@pytest.mark.asyncio
async def test_refresh_access_token_when_expired(tmp_path: Path):
    video_file = tmp_path / "short.mp4"
    video_file.write_bytes(b"bytes")

    refresh_calls: list[httpx.Request] = []

    def refresh_token(request: httpx.Request) -> httpx.Response:
        refresh_calls.append(request)
        return httpx.Response(
            200,
            json={"access_token": "ya29.new-token", "expires_in": 3600},
        )

    def init_upload(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Location": "https://upload.example.com/resumable/new"},
        )

    def put_upload(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": "yt-new", "status": {"uploadStatus": "uploaded"}}
        )

    expired_config = _config(
        token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    client = _make_client(
        {
            "POST /token": refresh_token,
            "POST /upload/youtube/v3/videos": init_upload,
            "PUT https://upload.example.com/resumable/new": put_upload,
        },
        config=expired_config,
    )

    result = await client.upload_video(
        YouTubeUploadRequest(
            snippet=YouTubeVideoSnippet(title="T", description="D"),
            video_path=str(video_file),
        )
    )

    assert result.video_id == "yt-new"
    assert len(refresh_calls) == 1
    assert client.config.credentials.access_token == "ya29.new-token"


@pytest.mark.asyncio
async def test_http_error_is_mapped():
    client = _make_client(
        {
            "GET /youtube/v3/videos?part=statistics&id=missing": lambda _: httpx.Response(
                404,
                json={"error": {"message": "Video not found"}},
            )
        }
    )

    with pytest.raises(YouTubeRequestError) as exc_info:
        await client.get_video_stats("missing")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_401_triggers_refresh_and_retry():
    api_auth_headers: list[str] = []
    refresh_calls: list[httpx.Request] = []
    stats_attempts = 0

    def refresh_token(request: httpx.Request) -> httpx.Response:
        refresh_calls.append(request)
        return httpx.Response(
            200,
            json={"access_token": "ya29.refreshed", "expires_in": 3600},
        )

    def get_stats(request: httpx.Request) -> httpx.Response:
        nonlocal stats_attempts
        stats_attempts += 1
        api_auth_headers.append(request.headers.get("Authorization", ""))
        if stats_attempts == 1:
            return httpx.Response(
                401,
                json={"error": {"message": "Invalid Credentials"}},
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "yt-1",
                        "statistics": {
                            "viewCount": "10",
                            "likeCount": "1",
                            "commentCount": "0",
                        },
                    }
                ]
            },
        )

    client = _make_client(
        {
            "POST /token": refresh_token,
            "GET /youtube/v3/videos?part=statistics&id=yt-1": get_stats,
        }
    )

    stats = await client.get_video_stats("yt-1")

    assert stats.view_count == 10
    assert len(refresh_calls) == 1
    assert stats_attempts == 2
    assert api_auth_headers[1] == "Bearer ya29.refreshed"
    assert client.config.credentials.access_token == "ya29.refreshed"


@pytest.mark.asyncio
async def test_auth_error_when_401_persists_after_refresh():
    def refresh_token(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "ya29.refreshed", "expires_in": 3600},
        )

    def get_stats(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": {"message": "Invalid Credentials"}},
        )

    client = _make_client(
        {
            "POST /token": refresh_token,
            "GET /youtube/v3/videos?part=statistics&id=yt-1": get_stats,
        }
    )

    with pytest.raises(YouTubeAuthError):
        await client.get_video_stats("yt-1")


def test_build_snippet_adds_shorts_tag_and_description_suffix():
    video = MagicMock()
    video.hook_text = "Save money daily"
    video.caption = "Five tips for budgeting"
    video.generated_hashtags = ["#finance", "#tips"]

    snippet = _build_snippet(video, YouTubePlatformSettings(category_id="22"))

    assert snippet.title == "Save money daily"
    assert snippet.description.endswith("#Shorts")
    assert "Shorts" in snippet.tags
    assert "finance" in snippet.tags


@pytest.mark.asyncio
async def test_uploader_delegates_to_client(tmp_path: Path):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"clip")

    captured: dict = {}

    class FakeClient:
        async def upload_video(self, request: YouTubeUploadRequest):
            captured["request"] = request
            return MagicMock(video_id="uploaded-id", status="uploaded")

    def client_factory(credentials: dict) -> FakeClient:
        captured["credentials"] = credentials
        return FakeClient()

    video = MagicMock()
    video.id = 42
    video.hook_text = "Hook"
    video.caption = "Caption"
    video.generated_hashtags = ["#test"]
    video.video_path = str(video_file)

    platform_config = MagicMock()
    platform_config.credentials_json = {
        "access_token": "token",
        "refresh_token": "refresh",
        "client_id": "id",
        "client_secret": "secret",
    }
    platform_config.platform_specific_settings = {
        "privacy_status": "unlisted",
        "category_id": "24",
    }

    uploader = YouTubeShortsUploader(client_factory=client_factory)
    video_id = await uploader.upload(
        UploadContext(video=video, platform_config=platform_config)
    )

    assert video_id == "uploaded-id"
    assert captured["request"].privacy_status == "unlisted"
    assert captured["request"].snippet.category_id == "24"
    assert captured["request"].video_path == str(video_file)
