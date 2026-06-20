from __future__ import annotations

from typing import Protocol, runtime_checkable

from ze_ingestion.types import RawContent

__all__ = ["Fetcher"]


@runtime_checkable
class Fetcher(Protocol):
    url_patterns: list[str]

    async def fetch(self, url: str) -> RawContent: ...
