from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from src.core.config import TikTokConfig
from src.core.http_client import HttpClient
from src.integrations.tiktok.client import (
    TikTokClient,
    TikTokRequestError,
    TikTokTimeoutError,
    TikTokUploadError,
)
from src.schemas.tiktok import (
    TikTokFileSourceInfo,
    TikTokPostInfo,
    TikTokPublishStatus,
)


def _tiktok_envelope(
    data: dict | None = None, *, code: str = "ok", message: str = ""
) -> dict:
    return {
        "data": data,
        "error": {"code": code, "message": message, "log_id": "test-log"},
    }


def _make_client(
    handlers: dict[str, Callable[[httpx.Request], httpx.Response]],
    *,
    poll_interval: float = 0.01,
    poll_timeout: float = 0.5,
) -> TikTokClient:
    def handler(request: httpx.Request) -> httpx.Response:
        route_key = f"{request.method} {request.url.path}"
        if route_key in handlers:
            return handlers[route_key](request)
        if request.method == "PUT":
            put_handler = handlers.get("PUT upload")
            if put_handler:
                return put_handler(request)
        return httpx.Response(
            404, json=_tiktok_envelope(code="not_found", message="route not found")
        )

    transport = httpx.MockTransport(handler)
    config = TikTokConfig(
        access_token="test-token",
        poll_interval=poll_interval,
        poll_timeout=poll_timeout,
    )

    def client_factory() -> HttpClient:
        return HttpClient(
            base_url=config.base_url,
            transport=transport,
            headers={
                "Authorization": f"Bearer {config.access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            http2=False,
        )

    return TikTokClient(
        config, client_factory=client_factory, upload_transport=transport
    )


@pytest.mark.asyncio
async def test_direct_post_init_upload_and_status_poll():
    poll_count = {"value": 0}

    def status_fetch(_: httpx.Request) -> httpx.Response:
        poll_count["value"] += 1
        status = (
            TikTokPublishStatus.PUBLISH_COMPLETE.value
            if poll_count["value"] >= 2
            else TikTokPublishStatus.PROCESSING_UPLOAD.value
        )
        payload = {"status": status, "publicaly_available_post_id": ["7123456789"]}
        return httpx.Response(200, json=_tiktok_envelope(payload))

    client = _make_client(
        {
            "POST /v2/post/publish/video/init/": lambda _: httpx.Response(
                200,
                json=_tiktok_envelope(
                    {
                        "publish_id": "v_pub_file~v2.123",
                        "upload_url": "https://open-upload.tiktokapis.com/video/?upload_id=1",
                    }
                ),
            ),
            "PUT upload": lambda request: httpx.Response(
                200,
                content=b"",
                request=request,
            ),
            "POST /v2/post/publish/status/fetch/": status_fetch,
        }
    )

    post_info = TikTokPostInfo(title="Test #fyp", privacy_level="SELF_ONLY")
    source_info = TikTokFileSourceInfo(video_size=12, chunk_size=12)
    result = await client.upload_direct_post(
        post_info=post_info,
        source_info=source_info,
        video_bytes=b"fake-video-mp4",
    )

    assert result.publish_id == "v_pub_file~v2.123"
    assert result.platform_video_id == "7123456789"
    assert poll_count["value"] >= 2


@pytest.mark.asyncio
async def test_inbox_upload_init_put_and_status_poll():
    poll_count = {"value": 0}
    uploaded = {"called": False}

    def status_fetch(_: httpx.Request) -> httpx.Response:
        poll_count["value"] += 1
        return httpx.Response(
            200,
            json=_tiktok_envelope(
                {"status": TikTokPublishStatus.SEND_TO_USER_INBOX.value}
            ),
        )

    def put_upload(request: httpx.Request) -> httpx.Response:
        uploaded["called"] = True
        assert request.headers.get("content-type") == "video/mp4"
        assert request.content == b"inbox-video-bytes"
        return httpx.Response(200, content=b"", request=request)

    client = _make_client(
        {
            "POST /v2/post/publish/inbox/video/init/": lambda _: httpx.Response(
                200,
                json=_tiktok_envelope(
                    {
                        "publish_id": "v_inbox_file~v2.456",
                        "upload_url": "https://open-upload.tiktokapis.com/video/?upload_id=2",
                    }
                ),
            ),
            "PUT upload": put_upload,
            "POST /v2/post/publish/status/fetch/": status_fetch,
        }
    )

    source_info = TikTokFileSourceInfo(video_size=17, chunk_size=17)
    result = await client.upload_inbox(
        source_info=source_info,
        video_bytes=b"inbox-video-bytes",
    )

    assert uploaded["called"] is True
    assert result.publish_id == "v_inbox_file~v2.456"
    assert result.platform_video_id is None
    assert poll_count["value"] == 1


@pytest.mark.asyncio
async def test_fetch_publish_status_failed_raises_upload_error():
    client = _make_client(
        {
            "POST /v2/post/publish/status/fetch/": lambda _: httpx.Response(
                200,
                json=_tiktok_envelope(
                    {
                        "status": TikTokPublishStatus.FAILED.value,
                        "fail_reason": "file_format_check_failed",
                    }
                ),
            )
        }
    )

    with pytest.raises(TikTokUploadError) as exc_info:
        await client.wait_for_publish("v_pub_file~fail")

    assert "file_format_check_failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_wait_for_publish_timeout():
    client = _make_client(
        {
            "POST /v2/post/publish/status/fetch/": lambda _: httpx.Response(
                200,
                json=_tiktok_envelope(
                    {"status": TikTokPublishStatus.PROCESSING_UPLOAD.value}
                ),
            )
        },
        poll_interval=0.01,
        poll_timeout=0.05,
    )

    with pytest.raises(TikTokTimeoutError):
        await client.wait_for_publish("v_pub_file~slow")


@pytest.mark.asyncio
async def test_list_videos_and_query_videos():
    client = _make_client(
        {
            "POST /v2/video/list/": lambda request: httpx.Response(
                200,
                json=_tiktok_envelope(
                    {
                        "videos": [{"id": "111", "title": "First"}],
                        "cursor": 1643332803000,
                        "has_more": False,
                    }
                ),
            ),
            "POST /v2/video/query/": lambda _: httpx.Response(
                200,
                json=_tiktok_envelope(
                    {
                        "videos": [
                            {"id": "111", "title": "First", "view_count": 42},
                            {"id": "222", "title": "Second", "view_count": 7},
                        ]
                    }
                ),
            ),
        }
    )

    listed = await client.list_videos(max_count=10)
    queried = await client.query_videos(["111", "222"])

    assert listed.videos[0].id == "111"
    assert listed.has_more is False
    assert queried.videos[1].view_count == 7


@pytest.mark.asyncio
async def test_api_error_code_raises_request_error():
    client = _make_client(
        {
            "POST /v2/post/publish/inbox/video/init/": lambda _: httpx.Response(
                200,
                json=_tiktok_envelope(code="invalid_param", message="bad source_info"),
            )
        }
    )

    with pytest.raises(TikTokRequestError) as exc_info:
        await client.init_inbox_upload(
            TikTokFileSourceInfo(video_size=10, chunk_size=10)
        )

    assert exc_info.value.error_code == "invalid_param"


@pytest.mark.asyncio
async def test_build_post_info_from_video_metadata():
    from src.schemas.tiktok import build_post_info_from_video_metadata

    post_info = build_post_info_from_video_metadata(
        hook_text="Save money fast",
        caption="Three tips inside",
        hashtags=["#finance", "#fyp"],
    )

    assert "Save money fast" in (post_info.title or "")
    assert "Three tips inside" in (post_info.title or "")
    assert "#fyp" in (post_info.title or "")
