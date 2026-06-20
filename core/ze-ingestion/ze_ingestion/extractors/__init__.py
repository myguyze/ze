from __future__ import annotations

from typing import Protocol, runtime_checkable

from ze_ingestion.types import ContentType, ExtractionResult, ProcessedContent

__all__ = ["Extractor"]


@runtime_checkable
class Extractor(Protocol):
    content_types: list[ContentType]  # empty = handles ALL

    async def extract(self, content: ProcessedContent) -> ExtractionResult: ...
