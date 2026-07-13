from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class NotificationRow:
    """Persisted `notifications` table row (ze-proactive owned)."""

    id: str
    event_type: str
    source: str
    title: str
    body: str
    target_type: str | None
    target_id: str | None
    created_at: datetime
    read_at: datetime | None


@dataclass
class Notification:
    """Wire representation — REST list item / `notification` WS frame payload."""

    id: str
    event_type: str
    source: str
    title: str
    body: str
    target_type: str | None
    target_id: str | None
    created_at: datetime
    read: bool
