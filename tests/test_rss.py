from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.cruds.auth import ProfileCrud
from src.cruds.channel import ChannelCrud
from src.cruds.rss import (
    ChannelNewsConsumptionCrud,
    RssFeedCrud,
    RssNewsItemCrud,
)
from src.integrations.llm_manager.prompts.video_idea import build_video_idea_prompt
from src.models.channel import Channel
from src.pipeline.routers import news_availability_router
from src.pipeline.state import PipelineState
from src.schemas.rss import RssFeedItem

CHANNEL_DATA = {
    "name": "Tech News",
    "niche": "Technology",
    "target_audience": "Developers",
    "language": "en",
    "tone_of_voice": "informative",
    "system_prompt": "Explain tech news clearly",
    "daily_video_count": 1,
    "posting_hours": [],
    "base_hashtags": ["tech"],
    "is_active": True,
}


@pytest.fixture
async def profile_id(db_session: AsyncSession) -> int:
    from src.cruds.auth import UserCrud

    user = await UserCrud().create(
        db_session,
        {
            "email": f"rss_{datetime.now(timezone.utc).timestamp()}@test.com",
            "hashed_password": "hashed",
            "is_active": True,
            "is_verified": True,
        },
    )
    profile = await ProfileCrud().create(
        db_session, {"user_id": user.id, "tier": "free"}
    )
    return profile.id


@pytest.fixture
async def channel(db_session: AsyncSession, profile_id: int) -> Channel:
    channel = await ChannelCrud().create(
        db_session,
        {"profile_id": profile_id, **CHANNEL_DATA},
    )
    await db_session.commit()
    return channel


@pytest.fixture
async def second_channel(db_session: AsyncSession, profile_id: int) -> Channel:
    channel = await ChannelCrud().create(
        db_session,
        {
            "profile_id": profile_id,
            **{**CHANNEL_DATA, "name": "Crypto News"},
        },
    )
    await db_session.commit()
    return channel


@pytest.fixture
async def rss_feed(db_session: AsyncSession):
    feed = await RssFeedCrud().create(
        db_session,
        {
            "name": "Test Feed",
            "url": f"https://example.com/feed-{datetime.now(timezone.utc).timestamp()}.xml",
            "category": "tech",
            "is_active": True,
        },
    )
    await db_session.commit()
    return feed


async def _create_news(
    db_session: AsyncSession,
    feed_id: int,
    *,
    guid: str,
    title: str,
) -> object:
    return await RssNewsItemCrud().create(
        db_session,
        {
            "feed_id": feed_id,
            "guid": guid,
            "title": title,
            "summary": "Summary text",
            "link": f"https://example.com/{guid}",
            "author": "Author",
            "published_at": datetime.now(timezone.utc),
            "fetched_at": datetime.now(timezone.utc),
        },
    )


@pytest.mark.asyncio
async def test_upsert_item_deduplicates(
    db_session: AsyncSession,
    rss_feed,
):
    item = RssFeedItem(
        title="Breaking News",
        link="https://example.com/1",
        guid="guid-1",
        summary="Summary",
    )
    crud = RssNewsItemCrud()
    first = await crud.upsert_item(db_session, rss_feed.id, item)
    second = await crud.upsert_item(db_session, rss_feed.id, item)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_get_unused_for_channel_isolates_channels(
    db_session: AsyncSession,
    channel: Channel,
    second_channel: Channel,
    rss_feed,
):
    news = await _create_news(
        db_session, rss_feed.id, guid="shared-guid", title="Shared"
    )
    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    await RssFeedCrud().grant_feeds_to_channel(
        db_session, second_channel.id, [rss_feed.id]
    )

    await ChannelNewsConsumptionCrud().mark_selected(
        db_session,
        channel.id,
        news.id,
    )

    unused_channel_a = await RssNewsItemCrud().get_unused_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
        limit=10,
    )
    unused_channel_b = await RssNewsItemCrud().get_unused_for_channel(
        db_session,
        second_channel.id,
        max_age_days=7,
        limit=10,
    )

    assert unused_channel_a == []
    assert len(unused_channel_b) == 1
    assert unused_channel_b[0].id == news.id


@pytest.mark.asyncio
async def test_get_unused_respects_max_age(
    db_session: AsyncSession,
    channel: Channel,
    rss_feed,
):
    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    old_news = await RssNewsItemCrud().create(
        db_session,
        {
            "feed_id": rss_feed.id,
            "guid": "old-guid",
            "title": "Old",
            "summary": "",
            "link": "https://example.com/old",
            "author": "",
            "published_at": datetime.now(timezone.utc) - timedelta(days=30),
            "fetched_at": datetime.now(timezone.utc),
        },
    )
    unused = await RssNewsItemCrud().get_unused_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
        limit=10,
    )
    assert all(item.id != old_news.id for item in unused)


def test_news_availability_router_skip_when_required_but_missing():
    state: PipelineState = {
        "channel_id": 1,
        "news_required": True,
        "selected_news_item": None,
    }
    assert news_availability_router(state) == "skip"


def test_news_availability_router_continue_when_news_present():
    state: PipelineState = {
        "channel_id": 1,
        "news_required": True,
        "selected_news_item": {"id": 1, "title": "Story"},
    }
    assert news_availability_router(state) == "continue"


def test_news_availability_router_continue_when_not_required():
    state: PipelineState = {
        "channel_id": 1,
        "news_required": False,
        "selected_news_item": None,
    }
    assert news_availability_router(state) == "continue"


def test_build_video_idea_prompt_includes_news_block():
    test_channel = Channel(
        id=1,
        profile_id=1,
        **CHANNEL_DATA,
    )
    news_item = {
        "title": "AI Breakthrough",
        "summary": "A major model was released.",
        "link": "https://example.com/ai",
        "author": "Reporter",
    }
    _, user_prompt = build_video_idea_prompt(test_channel, news_item=news_item)
    assert "REQUIRED NEWS SOURCE" in user_prompt
    assert "AI Breakthrough" in user_prompt
    assert "https://example.com/ai" in user_prompt


@pytest.mark.asyncio
async def test_select_news_without_feeds_sets_optional_mode(
    db_session: AsyncSession,
    channel: Channel,
):
    from src.pipeline.nodes.news import select_news

    result = await select_news({"channel_id": channel.id})
    assert result["news_required"] is False
    assert result["selected_news_item"] is None


@pytest.mark.asyncio
async def test_select_news_with_feed_but_no_items_skips(
    db_session: AsyncSession,
    channel: Channel,
    rss_feed,
):
    from src.pipeline.nodes.news import select_news

    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    await db_session.commit()
    result = await select_news({"channel_id": channel.id})
    assert result["news_required"] is True
    assert result["selected_news_item"] is None


@pytest.mark.asyncio
async def test_select_news_picks_and_marks_consumption(
    db_session: AsyncSession,
    channel: Channel,
    rss_feed,
):
    from src.pipeline.nodes.news import select_news

    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    news = await _create_news(db_session, rss_feed.id, guid="pick-me", title="Pick Me")
    await db_session.commit()

    result = await select_news({"channel_id": channel.id})
    assert result["news_required"] is True
    assert result["selected_news_item"]["id"] == news.id
    assert result["news_consumption_id"] is not None

    unused = await RssNewsItemCrud().get_unused_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
        limit=10,
    )
    assert unused == []


@pytest.mark.asyncio
async def test_claim_next_news_for_channel_claims_single_item(
    db_session: AsyncSession,
    channel: Channel,
    rss_feed,
):
    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    news = await _create_news(
        db_session, rss_feed.id, guid="claim-me", title="Claim Me"
    )

    claimed = await RssNewsItemCrud().claim_next_news_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
    )
    assert claimed is not None
    news_item, consumption = claimed
    assert news_item.id == news.id
    assert consumption.channel_id == channel.id
    assert consumption.news_item_id == news.id

    second_claim = await RssNewsItemCrud().claim_next_news_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
    )
    assert second_claim is None


@pytest.mark.asyncio
async def test_claim_next_news_concurrent_no_duplicate_keys(
    db_session: AsyncSession,
    channel: Channel,
    rss_feed,
):
    from tests.conftest import test_session_maker

    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    for index in range(5):
        await _create_news(
            db_session,
            rss_feed.id,
            guid=f"concurrent-{index}",
            title=f"Story {index}",
        )
    await db_session.commit()

    async def claim_in_new_session():
        async with test_session_maker() as session:
            async with session.begin():
                return await RssNewsItemCrud().claim_next_news_for_channel(
                    session,
                    channel.id,
                    max_age_days=7,
                )

    results = await asyncio.gather(*[claim_in_new_session() for _ in range(5)])
    claimed = [result for result in results if result is not None]

    assert len(claimed) == 5
    news_ids = [news_item.id for news_item, _ in claimed]
    assert len(news_ids) == len(set(news_ids))


@pytest.mark.asyncio
async def test_fetch_feed_parses_sample_xml():
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Test</title>
        <item>
          <title>Sample Story</title>
          <link>https://example.com/story</link>
          <guid>story-guid</guid>
          <description>Story summary</description>
        </item>
      </channel>
    </rss>
    """
    mock_response = AsyncMock()
    mock_response.text = sample_xml
    mock_response.raise_for_status = lambda: None

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("src.integrations.rss_scrapping.HttpClient") as mock_http_client_cls:
        mock_http_client_cls.return_value = mock_client
        from src.core.config import settings
        from src.integrations.rss_scrapping import fetch_feed

        result = await fetch_feed("https://example.com/feed.xml")

    mock_http_client_cls.assert_called_once_with(
        timeout=settings.RSS_REQUEST_TIMEOUT,
        headers={"User-Agent": settings.RSS_USER_AGENT},
    )

    assert result.error is None
    assert len(result.items) == 1
    assert result.items[0].title == "Sample Story"
    assert result.items[0].guid == "story-guid"


@pytest.mark.asyncio
async def test_rss_api_grant_and_list(
    client,
    auth_headers: dict,
    db_session: AsyncSession,
):
    channel_resp = await client.post(
        "/api/v1/channels/",
        headers=auth_headers,
        json={
            "name": "RSS Channel",
            "niche": "Tech",
            "target_audience": "Devs",
            "language": "en",
            "tone_of_voice": "clear",
            "system_prompt": "News",
            "daily_video_count": 1,
            "posting_hours": [],
            "base_hashtags": ["news"],
        },
    )
    assert channel_resp.status_code == 201
    channel_id = channel_resp.json()["id"]

    feed = await RssFeedCrud().create(
        db_session,
        {
            "name": "API Feed",
            "url": f"https://api-feed.example.com/{datetime.now(timezone.utc).timestamp()}.xml",
            "category": "tech",
            "is_active": True,
        },
    )
    await db_session.commit()

    grant = await client.post(
        f"/api/v1/rss/channels/{channel_id}/feeds",
        headers=auth_headers,
        json={"feed_ids": [feed.id]},
    )
    assert grant.status_code == 200
    assert any(f["id"] == feed.id for f in grant.json())

    listed = await client.get(
        f"/api/v1/rss/channels/{channel_id}/feeds",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert any(f["id"] == feed.id for f in listed.json())


@pytest.mark.asyncio
async def test_release_consumption_allows_reclaim(
    db_session: AsyncSession,
    channel: Channel,
    rss_feed,
):
    await RssFeedCrud().grant_feeds_to_channel(db_session, channel.id, [rss_feed.id])
    news = await _create_news(
        db_session, rss_feed.id, guid="reclaim-me", title="Reclaim Me"
    )

    first_claim = await RssNewsItemCrud().claim_next_news_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
    )
    assert first_claim is not None
    _, consumption = first_claim
    assert consumption.news_item_id == news.id

    unused_before_release = await RssNewsItemCrud().get_unused_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
        limit=10,
    )
    assert unused_before_release == []

    released = await ChannelNewsConsumptionCrud().release_consumption(
        db_session,
        consumption.id,
    )
    assert released is True

    second_claim = await RssNewsItemCrud().claim_next_news_for_channel(
        db_session,
        channel.id,
        max_age_days=7,
    )
    assert second_claim is not None
    reclaimed_news, new_consumption = second_claim
    assert reclaimed_news.id == news.id
    assert new_consumption.id != consumption.id


@pytest.mark.asyncio
async def test_persist_metadata_idempotent_skips_when_video_metadata_id_in_state():
    from src.pipeline.nodes.storage import persist_metadata

    state: PipelineState = {
        "channel_id": 1,
        "video_metadata_id": 42,
        "video_idea": {
            "title": "Test Idea",
            "hook": "Hook line",
            "key_points": ["point"],
            "suggested_keywords": ["kw"],
            "estimated_duration_seconds": 45,
            "mood": "calm",
        },
        "video_script": {
            "title": "Test Idea",
            "script_segments": ["segment"],
            "voiceover_text": "A" * 50,
            "hashtags": ["test"],
            "thumbnail_description": "thumb",
        },
    }

    mock_video_crud = MagicMock()
    with patch(
        "src.pipeline.nodes.storage.get_video_metadata_crud",
        return_value=mock_video_crud,
    ):
        result = await persist_metadata(state)

    mock_video_crud.create.assert_not_called()
    assert result["video_metadata_id"] == 42
    assert result["current_step"] == "persist_metadata"
