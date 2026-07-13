from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_news.sources.rss import RSSSource


def _make_entry(
    link="https://example.com/1",
    title="Test Title",
    summary="<p>Hello world</p>",
    published=None,
):
    entry = MagicMock()
    entry.link = link
    entry.title = title
    entry.summary = summary
    entry.published = published
    entry.description = None
    return entry


def _make_feed(entries):
    feed = MagicMock()
    feed.entries = entries
    return feed


@pytest.fixture
def source():
    return RSSSource(key="test", url="https://example.com/rss", tags=["global", "tech"])


async def test_fetch_returns_articles(source):
    entry = _make_entry()
    feed = _make_feed([entry])

    mock_response = MagicMock()
    mock_response.text = "<rss/>"
    mock_response.raise_for_status = MagicMock()

    with (
        patch("ze_news.sources.rss.httpx.AsyncClient") as mock_client,
        patch("ze_news.sources.rss.feedparser.parse", return_value=feed),
    ):
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        articles = await source.fetch(limit=10)

    assert len(articles) == 1
    assert articles[0].title == "Test Title"
    assert articles[0].summary == "Hello world"
    assert articles[0].source_key == "test"
    assert articles[0].tags == ["global", "tech"]
    assert articles[0].published_at.tzinfo == timezone.utc


async def test_fetch_skips_entry_without_url(source):
    entry = _make_entry(link=None)
    feed = _make_feed([entry])

    mock_response = MagicMock()
    mock_response.text = "<rss/>"
    mock_response.raise_for_status = MagicMock()

    with (
        patch("ze_news.sources.rss.httpx.AsyncClient") as mock_client,
        patch("ze_news.sources.rss.feedparser.parse", return_value=feed),
    ):
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        articles = await source.fetch()

    assert articles == []


async def test_fetch_returns_empty_on_http_error(source):
    with patch("ze_news.sources.rss.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(
                get=AsyncMock(side_effect=Exception("connection refused"))
            )
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        articles = await source.fetch()

    assert articles == []


async def test_fetch_respects_limit(source):
    entries = [
        _make_entry(link=f"https://example.com/{i}", title=f"Title {i}")
        for i in range(10)
    ]
    feed = _make_feed(entries)

    mock_response = MagicMock()
    mock_response.text = "<rss/>"
    mock_response.raise_for_status = MagicMock()

    with (
        patch("ze_news.sources.rss.httpx.AsyncClient") as mock_client,
        patch("ze_news.sources.rss.feedparser.parse", return_value=feed),
    ):
        mock_client.return_value.__aenter__ = AsyncMock(
            return_value=MagicMock(get=AsyncMock(return_value=mock_response))
        )
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        articles = await source.fetch(limit=3)

    assert len(articles) == 3
