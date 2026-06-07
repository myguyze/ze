from __future__ import annotations

from ze_core.orchestration.tool import ToolAccess, tool
from ze_news.store import NewsStore


@tool(access=ToolAccess.READ, description="Semantic search over the local news article store.")
async def search_news(
    news_store: NewsStore,
    query: str,
    limit: int = 10,
    tags: list[str] | None = None,
) -> list[dict]:
    articles = await news_store.search(query, limit=limit, tags=tags)
    return [
        {
            "title": a.title,
            "url": a.url,
            "source": a.source_key,
            "summary": a.summary,
            "published_at": a.published_at.isoformat(),
            "tags": a.tags,
        }
        for a in articles
    ]


@tool(access=ToolAccess.READ, description="Fetch the most recent headlines, optionally filtered by tag (e.g. 'global', 'local', 'tech').")
async def get_headlines(
    news_store: NewsStore,
    limit: int = 20,
    tags: list[str] | None = None,
) -> list[dict]:
    articles = await news_store.get_recent(limit=limit, tags=tags)
    return [
        {
            "title": a.title,
            "url": a.url,
            "source": a.source_key,
            "published_at": a.published_at.isoformat(),
            "tags": a.tags,
        }
        for a in articles
    ]
