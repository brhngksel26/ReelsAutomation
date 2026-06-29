import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cannot_access_other_users_channel(
    client: AsyncClient, auth_headers: dict
):
    channel = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Owner Channel",
            "niche": "Tech",
            "target_audience": "Devs",
            "language": "en",
            "tone_of_voice": "casual",
        },
    )
    assert channel.status_code == 201
    channel_id = channel.json()["id"]

    other_email = "otherowner@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": other_email, "password": "securepass123"},
    )
    other_login = await client.post(
        "/api/v1/auth/token",
        data={"username": other_email, "password": "securepass123"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    update = await client.put(
        f"/api/v1/channels/{channel_id}",
        headers=other_headers,
        json={"name": "Hijacked"},
    )
    assert update.status_code == 404
