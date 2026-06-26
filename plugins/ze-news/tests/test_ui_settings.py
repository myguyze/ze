from ze_news.ui.settings import build_news_settings


def test_build_news_settings_unconfigured():
    tree = build_news_settings(None)
    assert len(tree) == 1
    assert tree[0]["type"] == "col"


def test_build_news_settings_lists_sources():
    cfg = {
        "sources": [
            {"key": "bbc", "url": "https://example.com/rss", "tags": ["global"]},
        ],
        "fetch_schedule": "*/30 * * * *",
        "credibility": {"enabled": True},
        "personalization": {"enabled": False},
    }
    tree = build_news_settings(cfg)
    root = tree[0]
    assert root["type"] == "col"
    assert len(root["children"]) >= 2
