import pytest
from httpx import AsyncClient

from tests.platform_credentials_fixtures import INSTAGRAM_CREDENTIALS


@pytest.mark.asyncio
async def test_platform_connect_and_status(client: AsyncClient, auth_headers: dict):
    channel = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Platform Channel",
            "niche": "Tech",
            "target_audience": "All",
            "language": "en",
            "tone_of_voice": "casual",
        },
    )
    channel_id = channel.json()["id"]

    connect = await client.post(
        "/api/v1/platforms/connect",
        headers=auth_headers,
        json={
            "channel_id": channel_id,
            "platform_type": "instagram",
            "credentials_json": INSTAGRAM_CREDENTIALS,
            "platform_specific_settings": {"share_to_feed": True},
        },
    )
    assert connect.status_code == 201
    assert connect.json()["platform_type"] == "instagram"

    status = await client.get("/api/v1/platforms/status", headers=auth_headers)
    assert status.status_code == 200
    assert len(status.json()) >= 1
