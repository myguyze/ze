from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContentType(str, Enum):
    WEB_PAGE   = "web_page"
    VIDEO      = "video"
    AUDIO      = "audio"
    PDF        = "pdf"
    IMAGE      = "image"
    PLAIN_TEXT = "plain_text"
    DOCUMENT   = "document"
    UNKNOWN    = "unknown"


@dataclass
class IngestionRequest:
    url: str | None = None
    file_bytes: bytes | None = None
    mime_type: str | None = None
    label: str | None = None


@dataclass
class RawContent:
    content_type: ContentType
    source_url: str | None
    data: bytes
    mime_type: str


@dataclass
class ProcessedContent:
    content_type: ContentType
    source_url: str | None
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    summary: str
    facts: list[str]
    entities: list[str]
    tags: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    ingestion_id: str
    content_type: ContentType
    source_url: str | None
    summary: str
    facts_count: int
    entities_count: int
    tags: list[str]
