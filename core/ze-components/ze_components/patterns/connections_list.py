from __future__ import annotations

from ze_components.organisms.connections import (
    ConnectionEvidence,
    ConnectionItem,
    Connections,
    connections,
)


def connections_list(items: list[dict], title: str | None = None) -> Connections:
    """Build a Connections organism from raw dicts."""
    conn_items: list[ConnectionItem] = []
    for item in items:
        evidence = [
            ConnectionEvidence(
                label=ev["label"],
                kind=ev["kind"],
                date=ev.get("date"),
                source=ev.get("source"),
            )
            for ev in item.get("evidence", [])
        ]
        conn_items.append(
            ConnectionItem(
                summary=item["summary"],
                narrative=item["narrative"],
                relation=item["relation"],
                confidence=item["confidence"],
                evidence=evidence,
            )
        )
    return connections(conn_items, title)
