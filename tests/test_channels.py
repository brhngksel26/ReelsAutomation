import pytest
from httpx import AsyncClient

CHANNEL_PAYLOAD = {
    "name": "Finance Tips",
    "niche": "Finance",
    "target_audience": "Young professionals",
    "language": "en",
    "tone_of_voice": "motivational",
    "system_prompt": "Create reels",
    "daily_video_count": 1,
    "posting_hours": ["12:00:00"],
    "base_hashtags": ["finance"],
}


@pytest.mark.asyncio
async def test_channel_crud(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json=CHANNEL_PAYLOAD,
    )
    assert create.status_code == 201
    channel_id = create.json()["id"]

    listing = await client.get("/api/v1/channels/", headers=auth_headers)
    assert listing.status_code == 200
    assert any(c["id"] == channel_id for c in listing.json())

    update = await client.put(
        f"/api/v1/channels/{channel_id}",
        headers=auth_headers,
        json={"name": "Updated Name"},
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Updated Name"

    delete = await client.delete(
        f"/api/v1/channels/{channel_id}",
        headers=auth_headers,
    )
    assert delete.status_code == 204
