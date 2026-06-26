from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ze_calendar.reminders.store import Reminder
from ze_calendar.ui.page import build_reminders_page


def _reminder(**overrides) -> Reminder:
    defaults = {
        "id": uuid4(),
        "label": "Call João",
        "fire_at": datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc),
        "created_at": datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
        "sent": False,
        "sent_at": None,
    }
    defaults.update(overrides)
    return Reminder(**defaults)


def test_build_reminders_page_empty():
    tree = build_reminders_page([])
    assert len(tree) == 1
    assert tree[0]["type"] == "col"


def test_build_reminders_page_renders_pending():
    tree = build_reminders_page([_reminder(), _reminder(label="Send report")])
    root = tree[0]
    assert root["type"] == "col"
    assert len(root["children"]) == 2
    assert root["children"][0]["variant"] == "card"


def test_build_reminders_page_includes_past_section():
    tree = build_reminders_page(
        [
            _reminder(label="Upcoming task"),
            _reminder(label="Done task", sent=True),
        ]
    )
    root = tree[0]
    assert any(child.get("content") == "Past" for child in root["children"])
