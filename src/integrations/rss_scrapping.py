from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser

from src.core.config import settings
from src.core.http_client import HttpClient
from src.schemas.rss import RssFeedItem, RssFetchResult

logger = logging.getLogger(__name__)


def _parse_published_at(entry: feedparser.FeedParserDict) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    published = entry.get("published") or entry.get("updated")
    if not published:
        return None
    try:
        parsed = parsedate_to_datetime(published)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _entry_guid(entry: feedparser.FeedParserDict, link: str) -> str:
    guid = entry.get("id") or entry.get("guid")
    if guid:
        return str(guid)[:1000]
    return link[:1000]


def _entry_summary(entry: feedparser.FeedParserDict) -> str:
    summary = entry.get("summary") or entry.get("description") or ""
    return str(summary).strip()


def _parse_feed_content(content: str, feed_url: str) -> list[RssFeedItem]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(str(parsed.bozo_exception or "Invalid RSS feed"))

    items: list[RssFeedItem] = []
    for entry in parsed.entries[: settings.RSS_MAX_ITEMS_PER_FEED]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        items.append(
            RssFeedItem(
                title=title,
                link=link,
                guid=_entry_guid(entry, link),
                summary=_entry_summary(entry),
                author=(entry.get("author") or "").strip(),
                published_at=_parse_published_at(entry),
            )
        )
    return items


async def fetch_feed(feed_url: str) -> RssFetchResult:
    """Fetch and parse a single RSS feed URL."""
    try:
        async with HttpClient(
            timeout=settings.RSS_REQUEST_TIMEOUT,
            headers={"User-Agent": settings.RSS_USER_AGENT},
        ) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
            content = response.text
        items = _parse_feed_content(content, feed_url)
        logger.info("fetch_feed url=%s item_count=%s", feed_url, len(items))
        return RssFetchResult(feed_url=feed_url, items=items)
    except Exception as exc:
        logger.warning(
            "fetch_feed failed url=%s error=%s", feed_url, exc, exc_info=True
        )
        return RssFetchResult(feed_url=feed_url, items=[], error=str(exc))
