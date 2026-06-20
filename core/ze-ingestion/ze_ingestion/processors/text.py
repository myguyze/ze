from __future__ import annotations

from ze_ingestion.types import ContentType, ProcessedContent, RawContent


class TextProcessor:
    """Passthrough — treats raw bytes as UTF-8 plain text."""

    content_types: list[ContentType] = [
        ContentType.PLAIN_TEXT,
        ContentType.DOCUMENT,
        ContentType.UNKNOWN,
    ]

    async def process(self, raw: RawContent) -> ProcessedContent:
        text = raw.data.decode("utf-8", errors="replace")
        return ProcessedContent(
            content_type=raw.content_type,
            source_url=raw.source_url,
            text=text,
        )
