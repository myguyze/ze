from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ContactListItem(BaseModel):
    id: UUID
    name: str
    email: str | None = None
    notes: str | None = None


class PluginPageResponse(BaseModel):
    title: str
    tree: list[dict[str, Any]]
