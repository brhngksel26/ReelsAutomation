from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_video_schedule_upcoming_status(client: AsyncClient, auth_headers: dict):
    channel = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "Video Channel",
            "niche": "Motivation",
            "target_audience": "All",
            "language": "en",
            "tone_of_voice": "energetic",
        },
    )
    channel_id = channel.json()["id"]
    scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

    video = await client.post(
        "/api/v1/videos/schedule",
        headers=auth_headers,
        json={
            "channel_id": channel_id,
            "hook_text": "Hook line",
            "caption": "Caption",
            "generated_hashtags": ["motivation"],
            "scheduled_at": scheduled_at,
        },
    )
    assert video.status_code == 201
    video_id = video.json()["id"]
    assert video.json()["generation_status"] in ("pending", "completed")

    upcoming = await client.get("/api/v1/videos/upcoming", headers=auth_headers)
    assert upcoming.status_code == 200
    assert any(v["id"] == video_id for v in upcoming.json())

    status = await client.get(
        f"/api/v1/videos/{video_id}/status",
        headers=auth_headers,
    )
    assert status.status_code == 200
