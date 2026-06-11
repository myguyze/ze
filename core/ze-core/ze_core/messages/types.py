from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

MessageRole = Literal["user", "assistant"]


@dataclass
class Message:
    id: UUID
    role: MessageRole
    text: str | None
    components: list[dict[str, Any]]
    read: bool
    created_at: datetime
    thread_id: str | None
