"""Valid platform credential payloads for tests."""

from datetime import datetime, timezone

_FUTURE_EXPIRY = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()

INSTAGRAM_CREDENTIALS = {
    "access_token": "stub",
    "token_expires_at": _FUTURE_EXPIRY,
    "ig_user_id": "12345",
    "auth_type": "facebook_login",
}

YOUTUBE_CREDENTIALS = {
    "access_token": "stub",
    "refresh_token": "stub_refresh",
    "token_expires_at": _FUTURE_EXPIRY,
    "client_id": "stub_client",
    "client_secret": "stub_secret",
}

TIKTOK_CREDENTIALS = {
    "access_token": "stub",
    "refresh_token": "stub_refresh",
    "open_id": "stub_open_id",
    "token_expires_at": _FUTURE_EXPIRY,
}
