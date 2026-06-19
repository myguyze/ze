from __future__ import annotations

from ze_components.atoms import badge, caption, subheading, text
from ze_components.molecules import center, col
from ze_components.molecules.col import Col


def timeline(events: list[dict], title: str | None = None) -> Col:
    """Chronological event list with time badge and optional description per event."""
    rows: list = []
    for event in events:
        inner: list = [text(event["title"])]
        if event.get("description"):
            inner.append(caption(event["description"]))
        rows.append(center([badge(event["time"]), col(inner, gap="none")]))
    children: list = ([subheading(title)] if title else []) + rows
    return col(children, gap="md")
