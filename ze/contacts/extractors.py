"""
Pure helpers that parse ToolCall results into contact proposal dicts.

Each proposal matches the shape expected by _write_contact_proposals in
ze/orchestration/nodes/memory.py:
  name, classification, relationship, contact_info, confidence, confirmed
"""

from __future__ import annotations

import email.utils
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ze.agents.types import ToolCall

from ze.contacts.types import SOURCE_WEIGHTS


def extract_email_contacts(tool_calls: list[ToolCall]) -> list[dict]:
    """Return one proposal per unique sender seen in get_email results."""
    seen: set[str] = set()
    proposals: list[dict] = []

    for tc in tool_calls:
        if tc.tool_name != "get_email" or not tc.success or not isinstance(tc.result, dict):
            continue
        from_header = tc.result.get("from", "")
        if not from_header:
            continue

        name, addr = email.utils.parseaddr(from_header)
        addr = addr.lower().strip()
        if not addr or addr in seen:
            continue
        seen.add(addr)

        if not name:
            name = addr.split("@")[0].replace(".", " ").title()

        proposals.append({
            "name": name,
            "classification": "unknown",
            "relationship": "email contact",
            "contact_info": {"email": addr},
            "confidence": SOURCE_WEIGHTS["email"],
            "confirmed": False,
        })

    return proposals


def extract_calendar_contacts(tool_calls: list[ToolCall]) -> list[dict]:
    """Return one proposal per unique attendee across list_events / create_event results."""
    seen: set[str] = set()
    proposals: list[dict] = []

    for tc in tool_calls:
        if tc.tool_name not in ("list_events", "create_event") or not tc.success:
            continue

        events = tc.result if tc.tool_name == "list_events" else [tc.result]
        if not isinstance(events, list):
            continue

        for event in events:
            if not isinstance(event, dict):
                continue
            for attendee in event.get("attendees", []):
                if attendee.get("self"):
                    continue
                addr = (attendee.get("email") or "").lower().strip()
                if not addr or addr in seen:
                    continue
                seen.add(addr)

                name = attendee.get("displayName") or addr.split("@")[0].replace(".", " ").title()
                proposals.append({
                    "name": name,
                    "classification": "unknown",
                    "relationship": "calendar contact",
                    "contact_info": {"email": addr},
                    "confidence": SOURCE_WEIGHTS["calendar"],
                    "confirmed": False,
                })

    return proposals
