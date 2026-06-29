#!/usr/bin/env python3
"""End-to-end smoke test for Reels Automation API."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


def fail(step: str, response: httpx.Response) -> None:
    print(f"FAIL [{step}] {response.status_code}: {response.text}")
    sys.exit(1)


def main() -> None:
    email = f"smoke_{datetime.now().timestamp()}@example.com"
    password = "securepass123"
    client = httpx.Client(base_url=BASE_URL, timeout=30)

    print(f"Running smoke test against {BASE_URL}")

    register = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Smoke",
            "last_name": "Test",
        },
    )
    if register.status_code != 201:
        fail("register", register)
    print("OK register")

    login = client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": password},
    )
    if login.status_code != 200:
        fail("login", login)
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("OK login")

    me = client.get("/api/v1/users/me", headers=headers)
    if me.status_code != 200:
        fail("users/me", me)
    print("OK users/me")

    channel = client.post(
        "/api/v1/channels/",
        headers=headers,
        json={
            "name": "Finance Tips",
            "niche": "Finance",
            "target_audience": "Young professionals",
            "language": "en",
            "tone_of_voice": "motivational",
            "system_prompt": "Create engaging finance reels",
            "daily_video_count": 2,
            "posting_hours": ["12:00:00", "18:00:00"],
            "base_hashtags": ["finance", "money"],
        },
    )
    if channel.status_code != 201:
        fail("create channel", channel)
    channel_id = channel.json()["id"]
    print("OK create channel")

    platform = client.post(
        "/api/v1/platforms/connect",
        headers=headers,
        json={
            "channel_id": channel_id,
            "platform_type": "instagram",
            "credentials_json": {"access_token": "stub"},
            "platform_specific_settings": {"share_to_feed": True},
        },
    )
    if platform.status_code != 201:
        fail("connect platform", platform)
    print("OK connect platform")

    scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    video = client.post(
        "/api/v1/videos/schedule",
        headers=headers,
        json={
            "channel_id": channel_id,
            "hook_text": "3 money habits that changed my life",
            "caption": "Save this for later!",
            "generated_hashtags": ["finance", "tips"],
            "scheduled_at": scheduled_at,
        },
    )
    if video.status_code != 201:
        fail("schedule video", video)
    video_id = video.json()["id"]
    print("OK schedule video")

    upcoming = client.get("/api/v1/videos/upcoming", headers=headers)
    if upcoming.status_code != 200 or not upcoming.json():
        fail("upcoming videos", upcoming)
    print("OK upcoming videos")

    status = client.get(f"/api/v1/videos/{video_id}/status", headers=headers)
    if status.status_code != 200:
        fail("video status", status)
    print("OK video status")

    print("\nAll smoke tests passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
