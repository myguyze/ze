from __future__ import annotations

import asyncio
import inspect
from typing import Callable

from ze_components import context as _ctx
from ze_components.schema import build_render_schema
from ze_components.types import (
    CardComponent,
    ChoiceGroupComponent,
    ChoiceOption,
    ConnectAccountComponent,
    ConfirmAction,
    ConfirmComponent,
    ConsentComponent,
    ConsentScope,
    FormComponent,
    FormField,
    ListComponent,
    ListItem,
    MetricComponent,
    ProgressComponent,
    ProgressStep,
    ReviewComponent,
    ReviewItem,
    TableComponent,
    TimelineComponent,
    TimelineEvent,
)
from ze_agents.tool import ToolAccess, ToolSpec, _tools


def render_tool(component_cls: type, *, description: str) -> Callable:
    """Decorator that registers an async function as a render tool.

    Generates the LLM schema from the component dataclass, handles ContextVar
    append, and returns a human-readable confirmation string to the LLM.
    """
    schema = build_render_schema(component_cls)

    def _decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"render_tool {func.__name__!r} must be async")
        name = func.__name__

        # Idempotent: skip if already registered (module re-import after test cleanup)
        if name in _tools:
            return func

        async def _wrapper(**kwargs):
            component = await func(**kwargs)
            _ctx.append(component)
            label = (
                getattr(component, "title", None)
                or getattr(component, "prompt", None)
                or getattr(component, "label", None)
                or component_cls.__name__
            )
            list_field = next(
                (f for f in ("rows", "items", "events", "steps", "fields", "actions")
                 if hasattr(component, f)),
                None,
            )
            count = f" ({len(getattr(component, list_field))} items)" if list_field else ""
            return f"Rendered {component.type}: {label}{count}"

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


def _coerce(cls: type, val: object) -> object:
    """Dict → dataclass coercion. Raises TypeError on missing required fields."""
    return cls(**val) if isinstance(val, dict) else val


# ── Tool registrations ────────────────────────────────────────────────────────

@render_tool(TableComponent, description=(
    "Render structured data as a table. Use for 3+ rows. "
    "headers: list of column names. rows: list of rows, each a list of string cells. "
    "All values must be pre-formatted strings."
))
async def render_table(
    headers: list,
    rows: list,
    title: str | None = None,
    caption: str | None = None,
) -> TableComponent:
    return TableComponent(headers=headers, rows=rows, title=title, caption=caption)


@render_tool(MetricComponent, description=(
    "Render a single highlighted metric. Use for cost summaries, counts, or key numbers. "
    "value must be a pre-formatted string. trend example: '↓ 12% vs last week'."
))
async def render_metric(
    label: str,
    value: str,
    trend: str | None = None,
    note: str | None = None,
) -> MetricComponent:
    return MetricComponent(label=label, value=value, trend=trend, note=note)


@render_tool(ListComponent, description=(
    "Render a list of items with optional subtitles and status labels. "
    "Each item: {text (required), subtext (optional), status (optional)}."
))
async def render_list(
    items: list,
    title: str | None = None,
) -> ListComponent:
    return ListComponent(
        items=[_coerce(ListItem, i) for i in items],
        title=title,
    )


@render_tool(TimelineComponent, description=(
    "Render events in chronological order. "
    "Each event: {time (pre-formatted string, required), title (required), description (optional)}."
))
async def render_timeline(
    events: list,
    title: str | None = None,
) -> TimelineComponent:
    return TimelineComponent(
        events=[_coerce(TimelineEvent, e) for e in events],
        title=title,
    )


@render_tool(ProgressComponent, description=(
    "Render a step-by-step progress tracker. "
    "Each step: {label (required), status: 'done'|'active'|'pending' (required)}."
))
async def render_progress(
    title: str,
    steps: list,
) -> ProgressComponent:
    return ProgressComponent(
        title=title,
        steps=[_coerce(ProgressStep, s) for s in steps],
    )


@render_tool(ConfirmComponent, description=(
    "Render a confirmation prompt with action buttons. Cosmetic only — the user's "
    "tap is returned as a regular message, not a graph resume. "
    "Each action: {label (required), value (required), style: 'primary'|'secondary'|'danger' (optional)}."
))
async def render_confirm(
    prompt: str,
    actions: list,
) -> ConfirmComponent:
    return ConfirmComponent(
        prompt=prompt,
        actions=[_coerce(ConfirmAction, a) for a in actions],
    )


@render_tool(FormComponent, description=(
    "Render a structured input form. "
    "Each field: {id, label, field_type: 'text'|'number'|'date'|'select', "
    "placeholder (optional), options (required when field_type='select')}."
))
async def render_form(
    title: str,
    fields: list,
) -> FormComponent:
    return FormComponent(
        title=title,
        fields=[_coerce(FormField, f) for f in fields],
    )


@render_tool(CardComponent, description=(
    "Render a highlighted text card for notices, summaries, or callouts. "
    "style: 'info' (default) | 'warning' | 'success' | 'error'."
))
async def render_card(
    body: str,
    title: str | None = None,
    style: str = "info",
) -> CardComponent:
    return CardComponent(body=body, title=title, style=style)  # type: ignore[arg-type]


@render_tool(ChoiceGroupComponent, description=(
    "Render a choice group for interactive setup. "
    "Each option: {id, label, description (optional), recommended (optional)}."
))
async def render_choice_group(
    id: str,
    title: str,
    options: list,
    allow_multiple: bool = False,
    description: str | None = None,
    submit_label: str = "Continue",
) -> ChoiceGroupComponent:
    return ChoiceGroupComponent(
        id=id,
        title=title,
        options=[_coerce(ChoiceOption, o) for o in options],
        allow_multiple=allow_multiple,
        description=description,
        submit_label=submit_label,
    )


@render_tool(ConsentComponent, description=(
    "Render a consent prompt with explicit scopes. "
    "Each scope: {id, label, description, required}."
))
async def render_consent(
    id: str,
    title: str,
    body: str,
    scopes: list,
    accept_label: str = "Allow",
    reject_label: str = "Skip",
) -> ConsentComponent:
    return ConsentComponent(
        id=id,
        title=title,
        body=body,
        scopes=[_coerce(ConsentScope, s) for s in scopes],
        accept_label=accept_label,
        reject_label=reject_label,
    )


@render_tool(ConnectAccountComponent, description=(
    "Render an account connection prompt for onboarding or settings."
))
async def render_connect_account(
    id: str,
    provider: str,
    title: str,
    description: str,
    status: str = "not_connected",
    action_label: str = "Connect",
) -> ConnectAccountComponent:
    return ConnectAccountComponent(
        id=id,
        provider=provider,
        title=title,
        description=description,
        status=status,  # type: ignore[arg-type]
        action_label=action_label,
    )


@render_tool(ReviewComponent, description=(
    "Render a review list before saving durable setup details. "
    "Each item: {id, label, value, kind, plugin (optional)}."
))
async def render_review(
    id: str,
    title: str,
    items: list,
    approve_label: str = "Save",
    reject_label: str = "Edit",
) -> ReviewComponent:
    return ReviewComponent(
        id=id,
        title=title,
        items=[_coerce(ReviewItem, i) for i in items],
        approve_label=approve_label,
        reject_label=reject_label,
    )
