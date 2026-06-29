from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from src.core.base_exception import CrudIntegrityError
from src.core.enums import SchedulingMode
from src.schemas.channel import ChannelCreateIn
from src.services.channel import create_channel


def _make_user(*, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, email="creator@example.com")


def _make_profile(*, profile_id: int = 10, user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=profile_id, user_id=user_id)


def _make_channel(*, channel_id: int = 100, profile_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        id=channel_id,
        profile_id=profile_id,
        name="Celeb Spill",
        niche="celebrity news",
        target_audience="Gen Z",
        language="en",
        tone_of_voice="snappy",
        system_prompt="",
        daily_video_count=1,
        posting_hours=[],
        base_hashtags=[],
        is_active=True,
        scheduling_mode=SchedulingMode.FIXED_HOURS,
        rss_interval_minutes=30,
        rss_max_videos_per_day=20,
    )


class FakeProfileRepository:
    def __init__(self, profile: SimpleNamespace | None = None) -> None:
        self.profile = profile

    async def get_by_user_id(self, db, user_id: int) -> SimpleNamespace | None:
        if self.profile is None:
            return None
        if self.profile.user_id != user_id:
            return None
        return self.profile


class FakeChannelRepository:
    def __init__(self, *, fail_on_create: bool = False) -> None:
        self.created: list[dict] = []
        self.fail_on_create = fail_on_create
        self._next_id = 1

    async def create(self, db, data: dict) -> SimpleNamespace:
        if self.fail_on_create:
            raise CrudIntegrityError("channel name already exists")

        self.created.append(data)
        channel = _make_channel(channel_id=self._next_id, profile_id=data["profile_id"])
        channel.name = data["name"]
        channel.niche = data["niche"]
        channel.target_audience = data["target_audience"]
        channel.language = data["language"]
        channel.tone_of_voice = data["tone_of_voice"]
        self._next_id += 1
        return channel


@pytest.fixture
def channel_data() -> ChannelCreateIn:
    return ChannelCreateIn(
        name="Celeb Spill",
        niche="celebrity news",
        target_audience="Gen Z",
        language="en",
        tone_of_voice="snappy",
    )


@pytest.mark.asyncio
async def test_create_channel_uses_profile_id(channel_data):
    user = _make_user()
    profile = _make_profile(user_id=user.id)
    profile_repo = FakeProfileRepository(profile)
    channel_repo = FakeChannelRepository()

    channel = await create_channel(
        MagicMock(),
        user,
        channel_data,
        profile_crud=profile_repo,
        channel_crud=channel_repo,
    )

    assert channel.name == channel_data.name
    assert channel.profile_id == profile.id
    assert channel_repo.created == [
        {"profile_id": profile.id, **channel_data.model_dump()}
    ]


@pytest.mark.asyncio
async def test_create_channel_requires_profile(channel_data):
    user = _make_user()
    profile_repo = FakeProfileRepository(profile=None)
    channel_repo = FakeChannelRepository()

    with pytest.raises(HTTPException) as exc_info:
        await create_channel(
            MagicMock(),
            user,
            channel_data,
            profile_crud=profile_repo,
            channel_crud=channel_repo,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Profile not found"
    assert channel_repo.created == []


@pytest.mark.asyncio
async def test_create_channel_maps_integrity_error_to_conflict(channel_data):
    user = _make_user()
    profile = _make_profile(user_id=user.id)
    profile_repo = FakeProfileRepository(profile)
    channel_repo = FakeChannelRepository(fail_on_create=True)

    with pytest.raises(HTTPException) as exc_info:
        await create_channel(
            MagicMock(),
            user,
            channel_data,
            profile_crud=profile_repo,
            channel_crud=channel_repo,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "channel name already exists"
