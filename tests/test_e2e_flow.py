from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.platform_credentials_fixtures import TIKTOK_CREDENTIALS


@pytest.mark.asyncio
async def test_full_e2e_flow(client: AsyncClient):
    email = f"e2e_{datetime.now(timezone.utc).timestamp()}@example.com"
    password = "securepass123"

    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "E2E",
            "last_name": "User",
        },
    )
    assert register.status_code == 201

    login = await client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200

    channel = await client.post(
        "/api/v1/channels/",
        headers=headers,
        json={
            "name": "E2E Channel",
            "niche": "Finance",
            "target_audience": "Everyone",
            "language": "en",
            "tone_of_voice": "friendly",
            "posting_hours": ["09:00:00"],
            "base_hashtags": ["e2e"],
        },
    )
    assert channel.status_code == 201
    channel_id = channel.json()["id"]

    platform = await client.post(
        "/api/v1/platforms/connect",
        headers=headers,
        json={
            "channel_id": channel_id,
            "platform_type": "tiktok",
            "credentials_json": TIKTOK_CREDENTIALS,
        },
    )
    assert platform.status_code == 201

    scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    video = await client.post(
        "/api/v1/videos/schedule",
        headers=headers,
        json={
            "channel_id": channel_id,
            "hook_text": "E2E hook",
            "caption": "E2E caption",
            "scheduled_at": scheduled_at,
        },
    )
    assert video.status_code == 201
    video_id = video.json()["id"]

    upcoming = await client.get("/api/v1/videos/upcoming", headers=headers)
    assert upcoming.status_code == 200

    status = await client.get(f"/api/v1/videos/{video_id}/status", headers=headers)
    assert status.status_code == 200
