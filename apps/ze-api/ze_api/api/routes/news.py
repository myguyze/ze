from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ze_api.api.schemas import ArticleItem, CredibilityFlagItem

router = APIRouter(tags=["news"])


@router.get(
    "/api/news",
    response_model=list[ArticleItem],
    summary="List recent news articles",
    description="Returns recent news articles from configured RSS sources, newest first.",
)
async def list_news(
    request: Request,
    limit: int = Query(default=30, ge=1, le=100),
    tag: str | None = Query(default=None, description="Filter by tag"),
) -> list[ArticleItem]:
    store = request.app.state.container._plugin_stores.get("news_store")
    if store is None:
        return []

    tags = [tag] if tag else None
    articles = await store.get_recent(limit=limit, tags=tags)

    return [
        ArticleItem(
            url=article.url,
            source_key=article.source_key,
            title=article.title,
            summary=article.summary,
            published_at=article.published_at,
            tags=article.tags,
            credibility_flags=[
                CredibilityFlagItem(
                    type=f.type,
                    label=f.label,
                    detail=f.detail,
                )
                for f in (article.credibility.high_confidence_flags if article.credibility else [])
            ],
        )
        for article in articles
    ]
