from __future__ import annotations

from typing import Protocol, runtime_checkable

from ze_ingestion.types import ContentType, ProcessedContent, RawContent

__all__ = ["Processor"]


@runtime_checkable
class Processor(Protocol):
    content_types: list[ContentType]

    async def process(self, raw: RawContent) -> ProcessedContent: ...
