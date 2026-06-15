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
    field_type: Literal[
        "text",
        "textarea",
        "number",
        "date",
        "select",
        "multiselect",
        "boolean",
        "chips",
    ] = "text"
    placeholder: str | None = None
    options: list[str] | None = None    # only for field_type == "select"
    required: bool = True
    help_text: str | None = None
    default_value: str | None = None


@dataclass
class ChoiceOption:
    id: str
    label: str
    description: str | None = None
    recommended: bool = False


@dataclass
class ConsentScope:
    id: str
    label: str
    description: str
    required: bool = True


@dataclass
class ReviewItem:
    id: str
    label: str
    value: str
    kind: str
    plugin: str | None = None


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
    id: str
    title: str
    fields: list[FormField]
    type: Literal["form"] = field(default="form", init=False)


@dataclass
class CardComponent:
    body: str
    title: str | None = None
    style: Literal["info", "warning", "success", "error"] = "info"
    type: Literal["card"] = field(default="card", init=False)


@dataclass
class ChoiceGroupComponent:
    id: str
    title: str
    options: list[ChoiceOption]
    allow_multiple: bool = False
    description: str | None = None
    submit_label: str = "Continue"
    type: Literal["choice_group"] = field(default="choice_group", init=False)


@dataclass
class ConsentComponent:
    id: str
    title: str
    body: str
    scopes: list[ConsentScope]
    accept_label: str = "Allow"
    reject_label: str = "Skip"
    type: Literal["consent"] = field(default="consent", init=False)


@dataclass
class ConnectAccountComponent:
    id: str
    provider: str
    title: str
    description: str
    status: Literal["not_connected", "connected", "error"] = "not_connected"
    action_label: str = "Connect"
    type: Literal["connect_account"] = field(default="connect_account", init=False)


@dataclass
class ReviewComponent:
    id: str
    title: str
    items: list[ReviewItem]
    approve_label: str = "Save"
    reject_label: str = "Edit"
    type: Literal["review"] = field(default="review", init=False)


# ── Registry (used by codegen + schema generator) ─────────────────────────────

COMPONENT_TYPES: list[type] = [
    TableComponent, MetricComponent, ListComponent, TimelineComponent,
    ProgressComponent, ConfirmComponent, FormComponent, CardComponent,
    ChoiceGroupComponent, ConsentComponent, ConnectAccountComponent, ReviewComponent,
]

SUB_ITEM_TYPES: list[type] = [
    ListItem, TimelineEvent, ProgressStep, ConfirmAction, FormField,
    ChoiceOption, ConsentScope, ReviewItem,
]
