from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ze_components.atoms import caption, error, info, muted, subheading, text
from ze_components.molecules import card, col
from ze_components.serialize import serialize_tree
from ze_news.types import Article


def _time_ago(published_at: datetime) -> str:
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    diff = now - published_at
    mins = int(diff.total_seconds() // 60)
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h ago"
    return f"{hrs // 24}d ago"


def _article_card(article: Article) -> object:
    header = col(
        [
            subheading(article.title),
            caption(f"{article.source_key} · {_time_ago(article.published_at)}"),
        ],
        gap="none",
    )
    body: list[object] = [header]
    if article.summary:
        body.append(muted(article.summary))
    flags = article.credibility.high_confidence_flags if article.credibility else []
    if flags:
        body.append(error(flags[0].label))
    elif article.tags:
        body.append(info(", ".join(article.tags[:3])))
    return card(body)


def build_news_page(articles: list[Article]) -> list[dict[str, Any]]:
    if not articles:
        children: list[object] = [
            text("No articles yet."),
            muted("Articles are fetched from your configured RSS sources every 30 minutes."),
        ]
    else:
        children = [_article_card(article) for article in articles]
    return serialize_tree([col(children)])
