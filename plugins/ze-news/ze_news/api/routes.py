from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ze_plugin.api_auth import require_api_key
from ze_news.api.schemas import ArticleItem, CredibilityFlagItem, PluginPageResponse
from ze_news.ui.page import build_news_page
from ze_news.ui.settings import build_news_settings

router = APIRouter(
    prefix="/api/v0", tags=["news"], dependencies=[Depends(require_api_key)]
)


@router.get(
    "/news",
    response_model=list[ArticleItem],
    operation_id="listNews",
    summary="List recent news articles",
    description="Returns recent news articles from configured RSS sources, newest first.",
)
async def list_news(
    request: Request,
    limit: int = Query(
        default=30, ge=1, le=100, description="Maximum articles to return"
    ),
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
                for f in (
                    article.credibility.high_confidence_flags
                    if article.credibility
                    else []
                )
            ],
        )
        for article in articles
    ]


@router.get(
    "/news/page",
    response_model=PluginPageResponse,
    operation_id="getNewsPage",
    summary="News overview page",
    description="Returns the server-driven UI tree for the news management screen.",
)
async def get_news_page(
    request: Request,
    limit: int = Query(
        default=50, ge=1, le=100, description="Maximum articles to return"
    ),
) -> PluginPageResponse:
    store = request.app.state.container._plugin_stores.get("news_store")
    if store is None:
        return PluginPageResponse(title="News", tree=build_news_page([]))

    articles = await store.get_recent(limit=limit)
    return PluginPageResponse(title="News", tree=build_news_page(articles))


@router.get(
    "/news/settings",
    response_model=PluginPageResponse,
    operation_id="getNewsSettings",
    summary="News settings panel",
    description="Returns the server-driven UI tree for the news settings section.",
)
async def get_news_settings(request: Request) -> PluginPageResponse:
    settings = request.app.state.settings
    news_cfg = (
        settings.config.get("news", {}) if getattr(settings, "config", None) else {}
    )
    if not news_cfg.get("enabled", True) or not news_cfg.get("sources"):
        news_cfg = None
    return PluginPageResponse(title="News", tree=build_news_settings(news_cfg))
