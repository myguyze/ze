"""News signal adapter and SignalSource implementation."""
from __future__ import annotations

import uuid
from datetime import datetime

from ze_memory.types import EntityRef, Signal
from ze_news.types import Article


class ArticleSignalAdapter:
    def to_signal(self, article: Article) -> Signal:
        entities = [
            EntityRef(name=tag, entity_type="topic")
            for tag in article.tags
            if tag and len(tag) >= 2
        ]
        return Signal(
            id=uuid.uuid4(),
            source="news",
            external_ref=article.url,
            title=article.title,
            summary=article.summary,
            occurred_at=article.published_at,
            entities=entities,
            magnitude=0.0,
        )


class NewsSignalSource:
    """SignalSource for the news domain.

    ``NewsFetchJob`` calls ``push()`` after each fetch run; ``poll()`` drains the
    buffer for the admission gate.  Watermark ownership stays with the caller.
    """

    source_key = "news"

    def __init__(self) -> None:
        self._adapter = ArticleSignalAdapter()
        self._pending: list[Signal] = []

    def push(self, articles: list[Article]) -> None:
        """Convert and buffer newly-fetched articles."""
        for article in articles:
            self._pending.append(self._adapter.to_signal(article))

    async def poll(self, since: datetime) -> list[Signal]:
        """Return and clear all buffered signals.

        ``since`` is accepted for protocol compliance; because ``push()`` is called
        immediately before ``poll()`` in the fetch cycle the buffer always contains
        only the current run's articles.
        """
        result = self._pending
        self._pending = []
        return result
