from __future__ import annotations

from datetime import datetime, timezone

from ze_news.types import Article, CredibilityFlag, CredibilityReport
from ze_news.ui.page import build_news_page


def _article(**overrides) -> Article:
    defaults = {
        "url": "https://example.com/a",
        "source_key": "bbc",
        "title": "Headline",
        "summary": "Summary text",
        "published_at": datetime.now(timezone.utc),
        "tags": ["ai"],
    }
    defaults.update(overrides)
    return Article(**defaults)


def test_build_news_page_empty():
    tree = build_news_page([])
    assert len(tree) == 1
    assert tree[0]["type"] == "col"


def test_build_news_page_renders_articles():
    tree = build_news_page([_article(), _article(title="Second")])
    root = tree[0]
    assert root["type"] == "col"
    assert len(root["children"]) == 2
    assert root["children"][0]["type"] == "col"
    assert root["children"][0]["variant"] == "card"


def test_build_news_page_includes_credibility_badge():
    report = CredibilityReport(
        flags=[
            CredibilityFlag(
                type="clickbait",
                label="Clickbait",
                detail="Sensational headline",
                source="heuristic",
                confidence="high",
            )
        ]
    )
    tree = build_news_page([_article(credibility=report)])
    card_children = tree[0]["children"][0]["children"]
    assert any(child.get("type") == "badge" for child in card_children)
