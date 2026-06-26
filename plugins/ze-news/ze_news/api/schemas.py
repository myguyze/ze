from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CredibilityFlagItem(BaseModel):
    type: str
    label: str
    detail: str


class ArticleItem(BaseModel):
    url: str
    source_key: str
    title: str
    summary: str
    published_at: datetime
    tags: list[str]
    credibility_flags: list[CredibilityFlagItem]


class PluginPageResponse(BaseModel):
    title: str
    tree: list[dict[str, Any]]
