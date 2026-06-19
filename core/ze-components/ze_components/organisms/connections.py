from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Literal


@dataclass
class ConnectionEvidence:
    label: str
    kind: str
    date: str | None = None
    source: str | None = None


@dataclass
class ConnectionItem:
    summary: str
    narrative: str
    relation: str
    confidence: float
    evidence: list[ConnectionEvidence] = dc_field(default_factory=list)


@dataclass
class Connections:
    connections: list[ConnectionItem]
    title: str = "Connected to your history"
    type: Literal["connections"] = dc_field(default="connections", init=False)


def connections(items: list[ConnectionItem], title: str | None = None) -> Connections:
    return Connections(
        connections=items,
        title=title or "Connected to your history",
    )
