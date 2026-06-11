from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ── Sub-item types ────────────────────────────────────────────────────────────

@dataclass
class ListItem:
    text: str
    subtext: str | None = None
    status: str | None = None


@dataclass
class TimelineEvent:
    time: str           # pre-formatted: "Today 14:00", "Mon 9 Jun"
    title: str
    description: str | None = None


@dataclass
class ProgressStep:
    label: str
    status: Literal["done", "active", "pending"] = "pending"


@dataclass
class ConfirmAction:
    label: str
    value: str          # opaque; returned to backend on tap
    style: Literal["primary", "secondary", "danger"] = "secondary"


@dataclass
class FormField:
    id: str
    label: str
    field_type: Literal["text", "number", "date", "select"] = "text"
    placeholder: str | None = None
    options: list[str] | None = None    # only for field_type == "select"


# ── Component types ───────────────────────────────────────────────────────────

@dataclass
class TableComponent:
    headers: list[str]
    rows: list[list[str]]
    title: str | None = None
    caption: str | None = None
    type: Literal["table"] = field(default="table", init=False)


@dataclass
class MetricComponent:
    label: str
    value: str
    trend: str | None = None
    note: str | None = None
    type: Literal["metric"] = field(default="metric", init=False)


@dataclass
class ListComponent:
    items: list[ListItem]
    title: str | None = None
    type: Literal["list"] = field(default="list", init=False)


@dataclass
class TimelineComponent:
    events: list[TimelineEvent]
    title: str | None = None
    type: Literal["timeline"] = field(default="timeline", init=False)


@dataclass
class ProgressComponent:
    title: str
    steps: list[ProgressStep]
    type: Literal["progress"] = field(default="progress", init=False)


@dataclass
class ConfirmComponent:
    prompt: str
    actions: list[ConfirmAction]
    type: Literal["confirm"] = field(default="confirm", init=False)


@dataclass
class FormComponent:
    title: str
    fields: list[FormField]
    type: Literal["form"] = field(default="form", init=False)


@dataclass
class CardComponent:
    body: str
    title: str | None = None
    style: Literal["info", "warning", "success", "error"] = "info"
    type: Literal["card"] = field(default="card", init=False)


# ── Registry (used by codegen + schema generator) ─────────────────────────────

COMPONENT_TYPES: list[type] = [
    TableComponent, MetricComponent, ListComponent, TimelineComponent,
    ProgressComponent, ConfirmComponent, FormComponent, CardComponent,
]

SUB_ITEM_TYPES: list[type] = [
    ListItem, TimelineEvent, ProgressStep, ConfirmAction, FormField,
]
