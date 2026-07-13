from __future__ import annotations

import asyncio
import dataclasses
import inspect
from typing import Callable

from ze_components import context as _ctx
from ze_components.organisms.connections import Connections
from ze_components.organisms.form import Form, form_field as _form_field
from ze_components.organisms.table import Table
from ze_components.patterns.card_notice import card_notice
from ze_components.patterns.choice_group import choice_group
from ze_components.patterns.confirm import confirm_prompt
from ze_components.patterns.connect_account import connect_account
from ze_components.patterns.connections_list import connections_list
from ze_components.patterns.consent import consent
from ze_components.patterns.list import list_items
from ze_components.patterns.metric import metric
from ze_components.patterns.progress_steps import progress_steps
from ze_components.patterns.review import review
from ze_components.patterns.timeline import timeline
from ze_components.schema import build_render_schema
from ze_agents.tool import ToolAccess, ToolSpec, _tools
from ze_logging import get_logger

log = get_logger(__name__)


# ── Private schema dataclasses (LLM-facing input contracts only) ───────────────


@dataclasses.dataclass
class _MetricSchema:
    label: str
    value: str
    trend: str | None = None
    note: str | None = None


@dataclasses.dataclass
class _ListItem:
    text: str
    subtext: str | None = None
    status: str | None = None


@dataclasses.dataclass
class _ListSchema:
    items: list[_ListItem]
    title: str | None = None


@dataclasses.dataclass
class _TimelineEvent:
    time: str
    title: str
    description: str | None = None


@dataclasses.dataclass
class _TimelineSchema:
    events: list[_TimelineEvent]
    title: str | None = None


@dataclasses.dataclass
class _ProgressStep:
    label: str
    status: str


@dataclasses.dataclass
class _ProgressSchema:
    title: str
    steps: list[_ProgressStep]


@dataclasses.dataclass
class _ConfirmAction:
    label: str
    value: str
    style: str = "secondary"


@dataclasses.dataclass
class _ConfirmSchema:
    prompt: str
    actions: list[_ConfirmAction]


@dataclasses.dataclass
class _CardSchema:
    body: str
    title: str | None = None
    style: str = "info"


@dataclasses.dataclass
class _ChoiceOption:
    id: str
    label: str
    description: str | None = None
    recommended: bool = False


@dataclasses.dataclass
class _ChoiceGroupSchema:
    id: str
    title: str
    options: list[_ChoiceOption]
    allow_multiple: bool = False
    description: str | None = None
    submit_label: str = "Continue"


@dataclasses.dataclass
class _ConsentScope:
    id: str
    label: str
    description: str
    required: bool = True


@dataclasses.dataclass
class _ConsentSchema:
    id: str
    title: str
    body: str
    scopes: list[_ConsentScope]
    accept_label: str = "Allow"
    reject_label: str = "Skip"


@dataclasses.dataclass
class _ConnectAccountSchema:
    id: str
    provider: str
    title: str
    description: str
    status: str = "not_connected"
    action_label: str = "Connect"


@dataclasses.dataclass
class _ReviewItem:
    label: str
    value: str


@dataclasses.dataclass
class _ReviewSchema:
    id: str
    title: str
    items: list[_ReviewItem]
    approve_label: str = "Save"
    reject_label: str = "Edit"


# ── render_tool decorator ─────────────────────────────────────────────────────


def render_tool(schema_cls: type, *, description: str) -> Callable:
    """Decorator that registers an async function as a render tool.

    schema_cls provides the LLM-facing JSON schema. The function returns a
    Primitive tree, which is appended to the ContextVar side-channel.
    """
    schema = build_render_schema(schema_cls)

    def _decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"render_tool {func.__name__!r} must be async")
        name = func.__name__

        if name in _tools:
            return func

        async def _wrapper(**kwargs):
            primitive = await func(**kwargs)
            _ctx.append(primitive)
            label = name.removeprefix("render_")
            return f"Rendered {label}"

        _wrapper.__name__ = name
        _wrapper.__doc__ = description
        _wrapper.__signature__ = inspect.signature(func)

        _tools[name] = ToolSpec(
            name=name,
            access=ToolAccess.READ,
            description=description,
            func=_wrapper,
            _schema_override=schema,
        )
        return _wrapper

    return _decorator


def _coerce_dict(val: object) -> dict:
    if isinstance(val, dict):
        return val
    raise TypeError(f"Expected dict, got {type(val).__name__}: {val!r}")


# ── Tool registrations ────────────────────────────────────────────────────────


@render_tool(
    Table,
    description=(
        "Render structured data as a table. Use for 3+ rows. "
        "headers: list of column names. rows: list of rows, each a list of string cells. "
        "All values must be pre-formatted strings."
    ),
)
async def render_table(
    headers: list,
    rows: list,
    title: str | None = None,
    caption: str | None = None,
) -> Table:
    return Table(headers=headers, rows=rows, title=title, caption=caption)


@render_tool(
    _MetricSchema,
    description=(
        "Render a single highlighted metric. Use for cost summaries, counts, or key numbers. "
        "value must be a pre-formatted string. trend example: '↓ 12% vs last week'."
    ),
)
async def render_metric(
    label: str,
    value: str,
    trend: str | None = None,
    note: str | None = None,
) -> object:
    return metric(label, value, trend, note)


@render_tool(
    _ListSchema,
    description=(
        "Render a list of items with optional subtitles and status labels. "
        "Each item: {text (required), subtext (optional), status (optional: 'done'|'active'|'error')}."
    ),
)
async def render_list(
    items: list,
    title: str | None = None,
) -> object:
    return list_items([_coerce_dict(i) for i in items], title)


@render_tool(
    _TimelineSchema,
    description=(
        "Render events in chronological order. "
        "Each event: {time (pre-formatted string, required), title (required), description (optional)}."
    ),
)
async def render_timeline(
    events: list,
    title: str | None = None,
) -> object:
    return timeline([_coerce_dict(e) for e in events], title)


@render_tool(
    _ProgressSchema,
    description=(
        "Render a step-by-step progress tracker. "
        "Each step: {label (required), status: 'done'|'active'|'pending' (required)}."
    ),
)
async def render_progress(
    title: str,
    steps: list,
) -> object:
    return progress_steps(title, [_coerce_dict(s) for s in steps])


@render_tool(
    _ConfirmSchema,
    description=(
        "Render a confirmation prompt with action buttons. Cosmetic only — the user's "
        "tap is returned as a regular message, not a graph resume. "
        "Each action: {label (required), value (required), style: 'primary'|'secondary'|'danger' (optional)}."
    ),
)
async def render_confirm(
    prompt: str,
    actions: list,
) -> object:
    return confirm_prompt(prompt, [_coerce_dict(a) for a in actions])


@render_tool(
    Form,
    description=(
        "Render a structured input form. "
        "Each field: {id, label, field_type: 'text'|'number'|'date'|'select', "
        "placeholder (optional), options (required when field_type='select')}."
    ),
)
async def render_form(
    id: str,
    title: str,
    fields: list,
) -> Form:
    coerced = [_coerce_dict(f) for f in fields]
    form_fields = [
        _form_field(
            id=f["id"],
            label=f["label"],
            field_type=f.get("field_type", "text"),
            placeholder=f.get("placeholder"),
            options=f.get("options"),
            required=f.get("required", True),
            help_text=f.get("help_text"),
            default_value=f.get("default_value"),
        )
        for f in coerced
    ]
    return Form(id=id, title=title, fields=form_fields)


@render_tool(
    _CardSchema,
    description=(
        "Render a highlighted text card for notices, summaries, or callouts. "
        "style: 'info' (default) | 'warning' | 'success' | 'error'."
    ),
)
async def render_card(
    body: str,
    title: str | None = None,
    style: str = "info",
) -> object:
    return card_notice(body, title, style)


@render_tool(
    _ChoiceGroupSchema,
    description=(
        "Render a choice group for interactive setup. "
        "Each option: {id, label, description (optional), recommended (optional)}."
    ),
)
async def render_choice_group(
    id: str,
    title: str,
    options: list,
    allow_multiple: bool = False,
    description: str | None = None,
    submit_label: str = "Continue",
) -> object:
    return choice_group(
        title, [_coerce_dict(o) for o in options], description, submit_label
    )


@render_tool(
    _ConsentSchema,
    description=(
        "Render a consent prompt with explicit scopes. "
        "Each scope: {id, label, description, required}."
    ),
)
async def render_consent(
    id: str,
    title: str,
    body: str,
    scopes: list,
    accept_label: str = "Allow",
    reject_label: str = "Skip",
) -> object:
    return consent(
        title, body, [_coerce_dict(s) for s in scopes], accept_label, reject_label
    )


@render_tool(
    _ConnectAccountSchema,
    description=("Render an account connection prompt for onboarding or settings."),
)
async def render_connect_account(
    id: str,
    provider: str,
    title: str,
    description: str,
    status: str = "not_connected",
    action_label: str = "Connect",
) -> object:
    return connect_account(id, provider, title, description, status, action_label)


@render_tool(
    _ReviewSchema,
    description=(
        "Render a review list before saving durable setup details. "
        "Each item: {label, value}."
    ),
)
async def render_review(
    id: str,
    title: str,
    items: list,
    approve_label: str = "Save",
    reject_label: str = "Edit",
) -> object:
    return review(
        id, title, [_coerce_dict(i) for i in items], approve_label, reject_label
    )


@render_tool(
    Connections,
    description=(
        "Render a set of cross-domain connections found between this conversation and the user's history. "
        "Each connection: {summary, narrative, relation ('pattern'|'causal_guess'|'tension'|'convergence'), "
        "confidence (0–1), evidence (optional list of {label, kind, date?, source?})}."
    ),
)
async def render_connections(
    connections: list,
    title: str | None = None,
) -> Connections:
    return connections_list([_coerce_dict(c) for c in connections], title)


_RENDER_TOOL_NAMES = tuple(
    sorted(name for name in _tools if name.startswith("render_"))
)
if _RENDER_TOOL_NAMES:
    log.info("render_tools_registered", tools=list(_RENDER_TOOL_NAMES))
