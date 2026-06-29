from datetime import datetime, timezone

import pytest

from src.core.enums import PlatformType
from src.schemas.platform_credentials import validate_credentials_json
from src.services.credentials_persistence import merge_refreshed_youtube_credentials
from src.services.media_url import is_public_url, resolve_public_video_url
from src.services.uploaders.base import UploadContext


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Skip PostgreSQL bootstrap from tests/conftest.py for isolated unit tests."""
    yield


def test_is_public_url():
    assert is_public_url("https://cdn.example.com/video.mp4") is True
    assert is_public_url("http://localhost/video.mp4") is True
    assert is_public_url("/storage/videos/1.mp4") is False
    assert is_public_url(None) is False


def test_resolve_public_video_url_without_base():
    assert resolve_public_video_url("https://cdn.example.com/video.mp4") == (
        "https://cdn.example.com/video.mp4"
    )
    assert resolve_public_video_url("/local/path.mp4") is None


def test_resolve_public_video_url_with_base(monkeypatch):
    monkeypatch.setenv("PUBLIC_MEDIA_BASE_URL", "https://cdn.example.com/media/")
    from src.core.config import TestSettings

    test_settings = TestSettings()
    monkeypatch.setattr("src.services.media_url.settings", test_settings)

    assert resolve_public_video_url("/storage/videos/7.mp4") == (
        "https://cdn.example.com/media/storage/videos/7.mp4"
    )


@pytest.mark.asyncio
async def test_uploader_resolves_local_path_with_public_base(monkeypatch):
    monkeypatch.setenv("PUBLIC_MEDIA_BASE_URL", "https://cdn.example.com/")
    from src.core.config import TestSettings

    test_settings = TestSettings()
    monkeypatch.setattr("src.services.media_url.settings", test_settings)

    ig_user_id = "17841400000000000"
    captured_url: list[str] = []

    async def fake_publish_reels(self, *, video_url, **kwargs):
        captured_url.append(video_url)
        return "media-from-base-url"

    import src.services.uploaders.instagram as uploader_module

    original_builder = uploader_module.build_instagram_client_from_credentials

    def patched_builder(credentials, **kwargs):
        from src.core.instagram_config import InstagramConfig
        from src.integrations.instagram.client import InstagramClient

        client = InstagramClient(InstagramConfig.from_credentials(credentials))
        client.publish_reels = fake_publish_reels.__get__(client, InstagramClient)
        return client

    uploader_module.build_instagram_client_from_credentials = patched_builder
    try:
        uploader = uploader_module.InstagramUploader()
        video = type(
            "Video",
            (),
            {
                "id": 9,
                "video_path": "/storage/videos/9.mp4",
                "caption": "CDN test",
                "generated_hashtags": [],
            },
        )()
        platform_config = type(
            "PlatformConfig",
            (),
            {
                "credentials_json": {
                    "access_token": "token",
                    "ig_user_id": ig_user_id,
                },
                "platform_specific_settings": {},
            },
        )()
        media_id = await uploader.upload(
            UploadContext(video=video, platform_config=platform_config)
        )
    finally:
        uploader_module.build_instagram_client_from_credentials = original_builder

    assert media_id == "media-from-base-url"
    assert captured_url == ["https://cdn.example.com/storage/videos/9.mp4"]


def test_merge_refreshed_youtube_credentials():
    expires = datetime(2099, 6, 1, 12, 0, tzinfo=timezone.utc)
    merged = merge_refreshed_youtube_credentials(
        {
            "access_token": "old",
            "refresh_token": "refresh",
            "client_id": "id",
            "client_secret": "secret",
        },
        "new-token",
        expires,
    )
    assert merged["access_token"] == "new-token"
    assert merged["refresh_token"] == "refresh"
    assert merged["token_expires_at"] == expires.isoformat()


def test_validate_credentials_json_rejects_invalid_instagram():
    with pytest.raises(ValueError, match="Invalid credentials"):
        validate_credentials_json(
            PlatformType.INSTAGRAM,
            {"access_token": "x"},  # missing required fields
        )


def test_validate_credentials_json_accepts_youtube():
    result = validate_credentials_json(
        PlatformType.YOUTUBE_SHORTS,
        {
            "access_token": "token",
            "refresh_token": "refresh",
            "token_expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
            "client_id": "id",
            "client_secret": "secret",
        },
    )
    assert result["access_token"] == "token"


def test_validate_credentials_json_rejects_youtube_without_token_expires_at():
    with pytest.raises(ValueError, match="Invalid credentials"):
        validate_credentials_json(
            PlatformType.YOUTUBE_SHORTS,
            {
                "access_token": "token",
                "refresh_token": "refresh",
                "client_id": "id",
                "client_secret": "secret",
            },
        )
