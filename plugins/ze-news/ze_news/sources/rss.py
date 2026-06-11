from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import feedparser
import httpx

from ze_agents.logging import get_logger
from ze_news.sources.base import NewsSource
from ze_news.types import Article

log = get_logger(__name__)

_FETCH_TIMEOUT = 10.0
_SUMMARY_MAX = 500


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(text: str) -> str:
    parser = _HTMLStripper()
    parser.feed(text)
    return parser.get_text()


def _parse_date(entry: object) -> datetime:
    published = getattr(entry, "published", None)
    if published:
        try:
            return parsedate_to_datetime(published).astimezone(timezone.utc)
        except Exception:
            pass
    updated = getattr(entry, "updated", None)
    if updated:
        try:
            return parsedate_to_datetime(updated).astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


class RSSSource(NewsSource):
    def __init__(self, key: str, url: str, tags: list[str]) -> None:
        self.key = key
        self._url = url
        self._tags = tags

    async def fetch(self, limit: int = 20) -> list[Article]:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=_FETCH_TIMEOUT) as client:
                response = await client.get(self._url)
                response.raise_for_status()
                text = response.text

            loop = asyncio.get_event_loop()
            feed = await asyncio.wait_for(
                loop.run_in_executor(None, feedparser.parse, text),
                timeout=_FETCH_TIMEOUT,
            )
        except Exception as exc:
            log.warning("rss_fetch_failed", source=self.key, error=str(exc))
            return []

        articles: list[Article] = []
        for entry in feed.entries[:limit]:
            url = getattr(entry, "link", None)
            title = getattr(entry, "title", None)
            if not url or not title:
                continue

            raw_summary = (
                getattr(entry, "summary", None)
                or getattr(entry, "description", None)
                or ""
            )
            summary = _strip_html(raw_summary)[:_SUMMARY_MAX]

            articles.append(Article(
                url=url,
                source_key=self.key,
                title=_strip_html(title),
                summary=summary,
                published_at=_parse_date(entry),
                tags=list(self._tags),
            ))

        return articles
