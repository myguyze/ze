"""CalendarSignalSource — Phase 60 second-domain emitter.

Emits upcoming calendar events as signals so the correlation engine can cross-
reference meetings with news and other domains (e.g. a meeting with an org that
also appears in a news signal lands in the same neighbourhood).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ze_memory.types import Signal


class CalendarSignalSource:
    """SignalSource backed by upcoming calendar reminders.

    Polls unsent calendar reminders and emits each as a Signal.  The admission
    gate decides relevance; this source only converts and filters by ``since``.
    """

    source_key = "calendar"

    def __init__(self, store: "CalendarReminderStore") -> None:  # noqa: F821
        self._store = store

    async def poll(self, since: datetime) -> list[Signal]:
        from ze_calendar.reminders.calendar_store import CalendarReminderStore  # noqa: F401

        reminders = await self._store.list_unsent()
        signals: list[Signal] = []
        for reminder in reminders:
            assessed = reminder.assessed_at
            if assessed.tzinfo is None:
                assessed = assessed.replace(tzinfo=timezone.utc)
            if assessed < since:
                continue
            fire_at = reminder.fire_at
            if fire_at.tzinfo is None:
                fire_at = fire_at.replace(tzinfo=timezone.utc)
            signals.append(
                Signal(
                    id=uuid.uuid4(),
                    source="calendar",
                    external_ref=reminder.event_id,
                    title=reminder.event_title,
                    summary=f"Upcoming: {reminder.event_title} ({reminder.label})",
                    occurred_at=fire_at,
                    magnitude=0.0,
                )
            )
        return signals
