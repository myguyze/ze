from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:
    id: str
    title: str | None
    preview: str | None
    created_at: datetime
    last_active_at: datetime
