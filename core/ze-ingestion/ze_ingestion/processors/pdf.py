from __future__ import annotations

import io

from ze_ingestion.errors import ProcessError
from ze_ingestion.types import ContentType, ProcessedContent, RawContent


class PdfProcessor:
    content_types: list[ContentType] = [ContentType.PDF]

    async def process(self, raw: RawContent) -> ProcessedContent:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ProcessError("pypdf not installed — cannot process PDF") from exc

        try:
            reader = PdfReader(io.BytesIO(raw.data))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p.strip() for p in pages if p.strip())
        except Exception as exc:
            raise ProcessError(f"PDF extraction failed: {exc}") from exc

        return ProcessedContent(
            content_type=raw.content_type,
            source_url=raw.source_url,
            text=text,
            metadata={"page_count": len(reader.pages)},
        )
