from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ze_calendar.reminders.store import Reminder
from ze_components.atoms import caption, label, muted, subheading, text
from ze_components.molecules import between, card, col
from ze_components.serialize import serialize_tree


def _format_fire_at(fire_at: datetime) -> str:
    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)
    return fire_at.astimezone().strftime("%d/%m/%y, %H:%M")


def _pending_card(reminder: Reminder) -> object:
    return card(
        [
            between(
                [
                    subheading(reminder.label),
                    caption(_format_fire_at(reminder.fire_at)),
                ]
            )
        ]
    )


def _past_card(reminder: Reminder) -> object:
    return card([muted(reminder.label)])


def build_reminders_page(reminders: list[Reminder]) -> list[dict[str, Any]]:
    pending = [r for r in reminders if not r.sent]
    past = [r for r in reminders if r.sent][:5]

    children: list[object] = []
    if not pending:
        children.append(text("No reminders. Ask Ze to set one."))
    else:
        children.extend(_pending_card(reminder) for reminder in pending)

    if past:
        children.append(label("Past"))
        children.extend(_past_card(reminder) for reminder in past)

    return serialize_tree([col(children)])
