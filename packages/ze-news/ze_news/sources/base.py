from __future__ import annotations

from abc import ABC, abstractmethod

from ze_news.types import Article


class NewsSource(ABC):
    key: str

    @abstractmethod
    async def fetch(self, limit: int = 20) -> list[Article]:
        """Fetch up to `limit` recent articles. Returns [] on any error."""
