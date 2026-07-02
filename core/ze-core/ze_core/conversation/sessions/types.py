from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Session:
    id: str
    title: str | None
    preview: str | None
    title_source: str | None
    created_at: datetime
    last_active_at: datetime


@dataclass
class SessionListPage:
    items: list[Session]
    next_before: datetime | None


@dataclass
class SessionSearchHit:
    session: Session
    match_source: str
    snippet: str | None
    rank: float
