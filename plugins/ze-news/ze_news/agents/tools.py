from __future__ import annotations

from ze_agents.tool import ToolAccess, tool
from ze_news.jobs.fetch import NewsFetchJob
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
    _diagnostic_query: bool = False,
    _min_preferences: int = 2,
) -> dict:
    if _diagnostic_query:
        return {
            "relevant": [],
            "discovery": [],
            "note": (
                "Diagnostic or preference-management query — answer from stored "
                "preferences, not headlines."
            ),
        }
    if personalized and _personalization_ctx is not None:
        relevant, discovery = await news_store.get_personalized(
            ctx=_personalization_ctx,
            limit=limit,
            tags=tags,
            min_facts=_min_preferences,
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


@tool(
    access=ToolAccess.READ,
    description=(
        "Trigger an immediate refresh of all RSS news sources, bypassing the normal "
        "30-minute fetch interval. Call this when the user asks for today's news or "
        "complains that headlines are stale. After calling this, use get_headlines to "
        "present the freshly fetched articles."
    ),
)
async def refresh_news(news_fetch_job: NewsFetchJob) -> dict:
    await news_fetch_job.run(force=True)
    return {"status": "ok", "message": "All news sources have been refreshed."}


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
