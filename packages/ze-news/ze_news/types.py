from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    url: str
    source_key: str
    title: str
    summary: str
    published_at: datetime
    tags: list[str] = field(default_factory=list)


@dataclass
class SourceConfig:
    key: str
    type: str
    url: str
    tags: list[str] = field(default_factory=list)
