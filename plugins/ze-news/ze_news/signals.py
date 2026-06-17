"""Adapter that converts a news Article into a memory Signal."""
from __future__ import annotations

import uuid

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
