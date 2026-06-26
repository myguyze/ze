from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ReminderListItem(BaseModel):
    id: UUID
    label: str
    fire_at: datetime
    fired: bool


class PluginPageResponse(BaseModel):
    title: str
    tree: list[dict[str, Any]]
