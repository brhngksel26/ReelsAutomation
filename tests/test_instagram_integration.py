from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from src.core.http_client import HttpClient
from src.integrations.instagram.client import InstagramClient
from src.schemas.instagram import (
    InstagramRequestError,
    InstagramUploadError,
    ReelsPublishParams,
)
from src.services.uploaders.base import UploadContext

try:
    from src.core.instagram_config import InstagramAuthType, InstagramConfig
except ImportError:  # pragma: no cover - legacy import path during refactor
    from src.schemas.instagram import InstagramAuthType, InstagramConfig

import src.services.uploaders.instagram as instagram_uploader_module
from src.services.media_url import is_public_url, resolve_public_video_url
from src.services.uploaders.instagram import (
    InstagramUploader,
    build_instagram_caption,
)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Skip PostgreSQL bootstrap from tests/conftest.py for isolated HTTP tests."""
    yield


@pytest.fixture(autouse=True)
def mock_celery_delay():
    yield


def _graph_route(method: str, path: str, api_version: str = "v21.0") -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    if not normalized.startswith(f"/{api_version}/"):
        normalized = f"/{api_version}{normalized}"
    return f"{method} {normalized}"


def _make_client(
    handlers: dict[str, Callable[[httpx.Request], httpx.Response]],
    *,
    auth_type: InstagramAuthType = InstagramAuthType.FACEBOOK_LOGIN,
    ig_user_id: str = "17841400000000000",
) -> InstagramClient:
    def handler(request: httpx.Request) -> httpx.Response:
        route_key = f"{request.method} {request.url.path}"
        if route_key not in handlers:
            return httpx.Response(
                404,
                json={
                    "error": {"message": f"Unhandled route: {route_key}", "code": 404}
                },
            )
        return handlers[route_key](request)

    transport = httpx.MockTransport(handler)
    config = InstagramConfig(
        access_token="test-token",
        ig_user_id=ig_user_id,
        auth_type=auth_type,
        request_timeout=30.0,
    )

    def client_factory() -> HttpClient:
        return HttpClient(
            base_url=config.graph_base_url,
            transport=transport,
            http2=False,
        )

    return InstagramClient(config, client_factory=client_factory)


@pytest.mark.asyncio
async def test_publish_reels_container_then_publish():
    ig_user_id = "17841400000000000"
    client = _make_client(
        {
            _graph_route(
                "POST", f"/{ig_user_id}/media"
            ): lambda request: httpx.Response(
                200,
                json={"id": "container-123"},
            ),
            _graph_route(
                "POST", f"/{ig_user_id}/media_publish"
            ): lambda request: httpx.Response(
                200,
                json={"id": "media-456"},
            ),
        },
        ig_user_id=ig_user_id,
    )

    media_id = await client.publish_reels(
        video_url="https://cdn.example.com/reel.mp4",
        caption="Test caption #reels",
        media_type="REELS",
    )

    assert media_id == "media-456"


@pytest.mark.asyncio
async def test_create_media_container_sends_reels_params():
    ig_user_id = "17841400000000000"
    captured: dict[str, str] = {}

    def capture_media(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        if request.content:
            captured.update(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, json={"id": "container-789"})

    client = _make_client(
        {_graph_route("POST", f"/{ig_user_id}/media"): capture_media},
        ig_user_id=ig_user_id,
    )

    result = await client.create_media_container(
        ReelsPublishParams(
            video_url="https://cdn.example.com/video.mp4",
            caption="Hello world",
            media_type="REELS",
        )
    )

    assert result.id == "container-789"
    assert captured.get("media_type") == "REELS"
    assert captured.get("video_url") == "https://cdn.example.com/video.mp4"
    assert captured.get("caption") == "Hello world"
    assert captured.get("access_token") == "test-token"


@pytest.mark.asyncio
async def test_get_insights_returns_parsed_metrics():
    media_id = "media-456"
    client = _make_client(
        {
            _graph_route("GET", f"/{media_id}/insights"): lambda _: httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "name": "reach",
                            "period": "lifetime",
                            "values": [{"value": 1200}],
                            "title": "Reach",
                        },
                        {
                            "name": "likes",
                            "period": "lifetime",
                            "values": [{"value": 85}],
                        },
                    ]
                },
            )
        }
    )

    insights = await client.get_insights(media_id)

    assert insights.media_id == media_id
    assert len(insights.insights) == 2
    assert insights.insights[0].name == "reach"
    assert insights.insights[0].values[0]["value"] == 1200


@pytest.mark.asyncio
async def test_list_comments_returns_parsed_comments():
    media_id = "media-456"
    client = _make_client(
        {
            _graph_route("GET", f"/{media_id}/comments"): lambda _: httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "comment-1",
                            "text": "Great reel!",
                            "username": "viewer1",
                            "timestamp": "2026-06-22T10:00:00+0000",
                        }
                    ]
                },
            )
        }
    )

    result = await client.list_comments(media_id)

    assert result.media_id == media_id
    assert len(result.comments) == 1
    assert result.comments[0].text == "Great reel!"
    assert result.comments[0].username == "viewer1"


@pytest.mark.asyncio
async def test_instagram_login_uses_graph_instagram_host():
    ig_user_id = "17841400000000000"
    seen_host: list[str] = []

    def capture_host(request: httpx.Request) -> httpx.Response:
        seen_host.append(request.url.host or "")
        return httpx.Response(200, json={"id": "container-ig-login"})

    transport = httpx.MockTransport(capture_host)
    config = InstagramConfig(
        access_token="ig-token",
        ig_user_id=ig_user_id,
        auth_type=InstagramAuthType.INSTAGRAM_LOGIN,
    )

    def client_factory() -> HttpClient:
        return HttpClient(
            base_url=config.graph_base_url,
            transport=transport,
            http2=False,
        )

    client = InstagramClient(config, client_factory=client_factory)
    await client.create_media_container(
        ReelsPublishParams(video_url="https://cdn.example.com/reel.mp4")
    )

    assert seen_host == ["graph.instagram.com"]


@pytest.mark.asyncio
async def test_http_error_is_mapped():
    ig_user_id = "17841400000000000"
    client = _make_client(
        {
            _graph_route("POST", f"/{ig_user_id}/media"): lambda _: httpx.Response(
                400,
                json={"error": {"message": "Invalid video URL", "code": 100}},
            )
        },
        ig_user_id=ig_user_id,
    )

    with pytest.raises(InstagramRequestError) as exc_info:
        await client.publish_reels(video_url="https://cdn.example.com/bad.mp4")

    assert exc_info.value.status_code == 400
    assert "Invalid video URL" in str(exc_info.value)
    assert exc_info.value.error_code == 100


@pytest.mark.asyncio
async def test_init_resumable_upload_requires_facebook_login():
    ig_user_id = "17841400000000000"
    client = _make_client(
        {}, auth_type=InstagramAuthType.INSTAGRAM_LOGIN, ig_user_id=ig_user_id
    )

    with pytest.raises(InstagramUploadError, match="facebook_login"):
        await client.init_resumable_upload(file_size=1024)


def test_public_url_helpers():
    assert is_public_url("https://cdn.example.com/video.mp4") is True
    assert is_public_url("/storage/videos/1.mp4") is False
    assert resolve_public_video_url("https://cdn.example.com/video.mp4") == (
        "https://cdn.example.com/video.mp4"
    )
    assert resolve_public_video_url("/local/path.mp4") is None


def test_build_instagram_caption():
    video = type(
        "Video",
        (),
        {
            "caption": "Save money daily",
            "generated_hashtags": ["#finance", "#reels"],
        },
    )()

    caption = build_instagram_caption(video)

    assert caption == "Save money daily\n\n#finance #reels"


@pytest.mark.asyncio
async def test_uploader_publish_flow_with_mock_transport():
    ig_user_id = "17841400000000000"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "container-uploader"})
        if request.method == "POST" and request.url.path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media-uploader"})
        return httpx.Response(404, json={"error": {"message": "not found"}})

    transport = httpx.MockTransport(handler)
    config = InstagramConfig(access_token="token", ig_user_id=ig_user_id)

    def client_factory() -> HttpClient:
        return HttpClient(
            base_url=config.graph_base_url, transport=transport, http2=False
        )

    uploader = InstagramUploader()
    video = type(
        "Video",
        (),
        {
            "id": 42,
            "video_path": "https://cdn.example.com/42.mp4",
            "caption": "Uploader test",
            "generated_hashtags": ["#test"],
        },
    )()
    platform_config = type(
        "PlatformConfig",
        (),
        {
            "credentials_json": {
                "access_token": "token",
                "ig_user_id": ig_user_id,
                "auth_type": "facebook_login",
            },
            "platform_specific_settings": {"media_type": "REELS"},
        },
    )()

    original_builder = instagram_uploader_module.build_instagram_client_from_credentials

    def patched_builder(credentials, **kwargs):
        return InstagramClient(
            InstagramConfig.from_credentials(credentials),
            client_factory=client_factory,
        )

    instagram_uploader_module.build_instagram_client_from_credentials = patched_builder
    try:
        media_id = await uploader.upload(
            UploadContext(video=video, platform_config=platform_config)
        )
    finally:
        instagram_uploader_module.build_instagram_client_from_credentials = (
            original_builder
        )

    assert media_id == "media-uploader"


@pytest.mark.asyncio
async def test_uploader_rejects_local_video_path():
    uploader = InstagramUploader()
    video = type(
        "Video",
        (),
        {
            "id": 7,
            "video_path": "/storage/videos/7.mp4",
            "caption": "Local only",
            "generated_hashtags": [],
        },
    )()
    platform_config = type(
        "PlatformConfig",
        (),
        {
            "credentials_json": {
                "access_token": "token",
                "ig_user_id": "17841400000000000",
            },
            "platform_specific_settings": {},
        },
    )()

    with pytest.raises(InstagramUploadError, match="publicly accessible"):
        await uploader.upload(
            UploadContext(video=video, platform_config=platform_config)
        )
