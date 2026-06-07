from __future__ import annotations

from ze_news.sources.base import NewsSource
from ze_news.types import SourceConfig


def build_registry(configs: list[SourceConfig]) -> "SourceRegistry":
    from ze_news.sources.rss import RSSSource

    _builders = {
        "rss": lambda c: RSSSource(key=c.key, url=c.url, tags=c.tags),
    }

    sources: list[NewsSource] = []
    for config in configs:
        builder = _builders.get(config.type)
        if builder is None:
            raise ValueError(f"Unknown news source type: {config.type!r}")
        sources.append(builder(config))

    return SourceRegistry(sources)


class SourceRegistry:
    def __init__(self, sources: list[NewsSource]) -> None:
        self._sources = sources
        self._by_key = {s.key: s for s in sources}

    def all(self) -> list[NewsSource]:
        return list(self._sources)

    def by_tag(self, tag: str) -> list[NewsSource]:
        return [s for s in self._sources if hasattr(s, "_tags") and tag in s._tags]

    def by_key(self, key: str) -> NewsSource | None:
        return self._by_key.get(key)
