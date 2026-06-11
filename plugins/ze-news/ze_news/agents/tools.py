from __future__ import annotations

from ze_core.orchestration.tool import ToolAccess, tool
from ze_news.store import NewsStore
from ze_news.types import PersonalizationContext


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


@tool(
    access=ToolAccess.READ,
    description=(
        "Fetch headlines from the local news store. When personalized=true (default), "
        "returns {'relevant': [...], 'discovery': [...]} ranked by your interests. "
        "When personalized=false, returns a plain recency-ordered list. "
        "Optionally filter by tag (e.g. 'global', 'local', 'tech')."
    ),
)
async def get_headlines(
    news_store: NewsStore,
    limit: int = 20,
    tags: list[str] | None = None,
    personalized: bool = True,
    _personalization_ctx: PersonalizationContext | None = None,
) -> dict:
    if personalized and _personalization_ctx is not None:
        relevant, discovery = await news_store.get_personalized(
            ctx=_personalization_ctx,
            limit=limit,
            tags=tags,
        )
        return {
            "relevant": [_article_dict(a) for a in relevant],
            "discovery": [_article_dict(a) for a in discovery],
        }

    articles = await news_store.get_recent(limit=limit, tags=tags)
    return {
        "relevant": [_article_dict(a) for a in articles],
        "discovery": [],
    }


def _article_dict(a) -> dict:
    result: dict = {
        "title": a.title,
        "url": a.url,
        "source": a.source_key,
        "published_at": a.published_at.isoformat(),
        "tags": a.tags,
        "credibility": None,
    }
    if a.credibility is not None:
        result["credibility"] = {
            "flags": [
                {
                    "type": f.type,
                    "label": f.label,
                    "detail": f.detail,
                    "confidence": f.confidence,
                }
                for f in a.credibility.flags
            ],
            "status": a.credibility.status,
        }
    return result
