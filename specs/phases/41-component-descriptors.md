# Component Descriptors — Spec

> **Package:** `ze-components` (new package, no ze deps) + `ze` (hook wiring, AgentState propagation)
> **Phase:** 41
> **Status:** Pending
> **Depends on:** Phase 40 ([40-native-ui-foundation.md](40-native-ui-foundation.md)), Phase 21 ([30-agent-harness.md](30-agent-harness.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze-components` package scaffold | 🔲 Pending |
| Component types (`types.py`) | 🔲 Pending |
| ContextVar collection (`context.py`) | 🔲 Pending |
| `@render_tool` decorator | 🔲 Pending |
| All 8 render tool registrations | 🔲 Pending |
| `_build_render_schema()` | 🔲 Pending |
| `ComponentCollectionHook` | 🔲 Pending |
| `AgentState.components` field + graph propagation | 🔲 Pending |
| `ToolSpec._schema_override` extension | 🔲 Pending |
| Code generation script | 🔲 Pending |
| `make generate-components` target | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

Ze agents currently return plain text. This phase gives agents the ability to emit
structured component descriptors — typed data shapes that the Flutter app renders as
native UI elements (tables, timelines, confirm modals, progress views, etc.).

Component emission is a **tool call**, not an output format. Agents call
`render_table(...)`, `render_confirm(...)`, etc. during their tool loop. The render tools
accumulate descriptors in a `ContextVar` side-channel that does not pollute the LLM's
message history. At the end of the agent loop, a `ComponentCollectionHook` drains the
`ContextVar` and makes the collected descriptors available to the graph, which forwards
them to `NativeAppInterface.send_message()`.

A code generation script turns Python component dataclasses into Dart `@freezed` classes,
keeping Python and Flutter in sync from a single source of truth.

---

## Responsibilities

- Define all component types as Python dataclasses in `ze_components/types.py`.
- Provide a `@render_tool` decorator that registers a tool, generates a precise nested
  LLM schema from the component dataclass fields, and handles ContextVar append
  automatically — no boilerplate in each tool function.
- Collect rendered components during the agent tool loop via a `ContextVar`.
- Drain collected components after each agent invocation via a `ComponentCollectionHook`
  (using the existing `on_loop_start` / `on_loop_end` harness hook points).
- Propagate components through `AgentState` to `NativeAppInterface.send_message()`.
- Provide a code generation script that emits Dart `@freezed` classes and a JSON schema
  document from the Python component type definitions.

---

## Out of Scope

- Flutter rendering of components — Phase 42.
- Component interaction callbacks (e.g. user submitting a form) — Phase 42.
- Streaming component updates (live-updating a progress bar) — future scope.
- Server-side validation of LLM-provided component data beyond Python `TypeError`.
- Components over Telegram — Telegram is removed in Phase 40.
- `render_confirm` integration with the existing `await_confirmation` graph pause —
  resolved below: `render_confirm` is cosmetic in this phase; the graph pause continues
  to use the existing `pending_confirmation` mechanism.

---

## Package Layout

### New package

```
packages/ze-components/
  pyproject.toml              ← no ze deps; stdlib only
  ze_components/
    __init__.py
    types.py                  ← component dataclasses + COMPONENT_TYPES registry
    context.py                ← ContextVar + begin_collection / collect_and_reset
    tools.py                  ← @render_tool decorator + all 8 tool registrations
    schema.py                 ← _build_render_schema() + JSON schema export

scripts/
  generate_components.py      ← Python → JSON schema + Dart @freezed codegen
```

### Changes to existing packages

```
packages/ze-core/
  ze_core/
    orchestration/
      tool.py                 ← add _schema_override: dict | None to ToolSpec

packages/ze/
  ze/
    components/
      hook.py                 ← ComponentCollectionHook(BaseHarnessHook)
    container.py              ← register ComponentCollectionHook; import render tools
    orchestration/
      nodes.py (or graph.py)  ← read hook.pop_components() after agent.run();
                                 write to AgentState["components"]
```

### Updated package dependency graph

```
ze-browser    (no ze deps)
ze-core       (no ze deps)
ze-components (no ze deps)
ze-personal   → ze-core
ze            → ze-core, ze-personal, ze-browser, ze-components
ze-finance    → ze-core, ze-personal
ze-legal      → ze-core, ze-personal
ze-news       → ze-core, ze-personal
```

---

## Component Types

All types share a fixed `type` discriminator (`init=False`). All scalar values are `str`.
Optional fields default to `None`. Sub-item lists are typed dataclasses — the LLM passes
dicts; render tools coerce them.

```python
# ze_components/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal


# ── Sub-item types ──────────────────────────────────────────────────────────

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
    status: Literal["done", "active", "pending"]

@dataclass
class ConfirmAction:
    label: str
    value: str          # opaque; returned to backend on tap
    style: Literal["primary", "secondary", "danger"] = "secondary"

@dataclass
class FormField:
    id: str
    label: str
    field_type: Literal["text", "number", "date", "select"]
    placeholder: str | None = None
    options: list[str] | None = None    # only for field_type == "select"


# ── Component types ─────────────────────────────────────────────────────────

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


# ── Registry (used by codegen + schema generator) ───────────────────────────

COMPONENT_TYPES: list[type] = [
    TableComponent, MetricComponent, ListComponent, TimelineComponent,
    ProgressComponent, ConfirmComponent, FormComponent, CardComponent,
]

SUB_ITEM_TYPES: list[type] = [
    ListItem, TimelineEvent, ProgressStep, ConfirmAction, FormField,
]
```

---

## ContextVar Collection

```python
# ze_components/context.py

from contextvars import ContextVar
from dataclasses import asdict
from typing import Any

_pending: ContextVar[list[dict[str, Any]]] = ContextVar("ze_components_pending")


def begin_collection() -> object:
    """Reset the pending list for the current async context. Returns a reset token."""
    return _pending.set([])


def append(component: object) -> None:
    """Append a rendered component dict. No-ops if called outside a collection context."""
    try:
        current = _pending.get()
    except LookupError:
        return
    _pending.set(current + [asdict(component)])  # type: ignore[arg-type]


def collect_and_reset(token: object) -> list[dict[str, Any]]:
    """Drain accumulated components, restore prior context state, and return the list."""
    try:
        result = list(_pending.get())
    except LookupError:
        result = []
    _pending.reset(token)  # type: ignore[arg-type]
    return result
```

`ContextVar` is async-safe: each coroutine inherits an independent snapshot of the
context at creation time. Render tools are directly awaited inside `_agentic_loop` (not
dispatched via `create_task`), so they share the same context as `on_loop_start`.

---

## `ToolSpec` Extension (ze-core)

`ToolSpec.llm_schema()` currently auto-generates only flat primitives. Render tools need
nested item schemas. Add one optional field:

```python
# ze_core/orchestration/tool.py

@dataclass
class ToolSpec:
    name: str
    access: ToolAccess
    description: str
    func: Callable
    _schema_override: dict | None = None    # new; default None preserves existing behaviour

    def llm_schema(self) -> dict:
        params = self._schema_override if self._schema_override is not None else _auto_schema(self.func)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            },
        }
```

No existing tool or test is affected — `_schema_override` defaults to `None`.

---

## `_build_render_schema()` and `@render_tool`

```python
# ze_components/schema.py

import dataclasses
import typing

_PY_TO_JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}

def _field_schema(annotation) -> dict:
    """Convert a single type annotation to a JSON schema fragment."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if annotation in _PY_TO_JSON:
        return {"type": _PY_TO_JSON[annotation]}

    if origin is list:
        item_type = args[0] if args else str
        return {"type": "array", "items": _field_schema(item_type)}

    if origin is typing.Union:  # handles X | None
        non_none = [a for a in args if a is not type(None)]
        return _field_schema(non_none[0]) if non_none else {"type": "string"}

    if dataclasses.is_dataclass(annotation):
        return _dataclass_schema(annotation)

    return {"type": "string"}   # fallback for Literal, unknown types


def _dataclass_schema(cls: type) -> dict:
    """Build a JSON schema object from a dataclass."""
    hints = typing.get_type_hints(cls)
    props: dict = {}
    required: list[str] = []
    for f in dataclasses.fields(cls):
        if not f.init:
            continue                        # skip type discriminator
        props[f.name] = _field_schema(hints[f.name])
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


def build_render_schema(component_cls: type) -> dict:
    """
    Build the full JSON schema parameters block for a render tool whose
    arguments match the component dataclass fields (excluding `type`).
    """
    return _dataclass_schema(component_cls)
```

```python
# ze_components/tools.py  (decorator section)

import asyncio
import inspect
from ze_components import context as _ctx
from ze_components.schema import build_render_schema
from ze_core.orchestration.tool import _tools, ToolSpec, ToolAccess
from ze_core.errors import AgentConfigError


def render_tool(component_cls: type, *, description: str):
    """
    Decorator for render tools.

    The decorated async function must accept only keyword arguments matching
    the component's __init__ (excluding `type`) and return a ComponentDescriptor
    instance. The decorator handles:
      - LLM schema generation from the component dataclass
      - ContextVar append
      - Human-readable confirmation string returned to the LLM
    """
    schema = build_render_schema(component_cls)

    def _decorator(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"render_tool {func.__name__!r} must be async")
        name = func.__name__
        if name in _tools:
            raise AgentConfigError(f"Duplicate tool name {name!r}")

        async def _wrapper(**kwargs):
            component = await func(**kwargs)
            _ctx.append(component)
            # Human-readable confirmation — the LLM sees this, not the raw descriptor
            label = getattr(component, "title", None) or getattr(component, "prompt", None) or component_cls.__name__
            list_field = next(
                (f for f in ("rows", "items", "events", "steps", "fields", "actions")
                 if hasattr(component, f)),
                None,
            )
            count = f" ({len(getattr(component, list_field))} items)" if list_field else ""
            return f"Rendered {component.type}: {label}{count}"

        _wrapper.__name__ = name
        _wrapper.__doc__ = description
        sig = inspect.signature(func)
        _wrapper.__signature__ = sig

        _tools[name] = ToolSpec(
            name=name,
            access=ToolAccess.READ,
            description=description,
            func=_wrapper,
            _schema_override=schema,
        )
        return _wrapper

    return _decorator
```

---

## Render Tool Registrations

```python
# ze_components/tools.py  (tool registration section)

from ze_components.types import (
    TableComponent, MetricComponent, ListComponent, TimelineComponent,
    ProgressComponent, ConfirmComponent, FormComponent, CardComponent,
    ListItem, TimelineEvent, ProgressStep, ConfirmAction, FormField,
)

def _coerce(cls, val):
    """Dict → dataclass coercion. Raises TypeError on missing required fields."""
    return cls(**val) if isinstance(val, dict) else val


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
```

---

## `ComponentCollectionHook`

The hook brackets each agent loop invocation. It stores collection tokens and results
keyed by `session_id`, making it safe for the single-user concurrent execution paths
(parallel subtask agents have distinct `session_id` values).

```python
# ze/components/hook.py

from ze_components import context as _ctx
from ze_core.orchestration.hooks import BaseHarnessHook, LoopStartEvent, LoopEndEvent


class ComponentCollectionHook(BaseHarnessHook):

    def __init__(self) -> None:
        self._tokens: dict[str, object] = {}
        self._results: dict[str, list[dict]] = {}

    async def on_loop_start(self, event: LoopStartEvent) -> None:
        token = _ctx.begin_collection()
        self._tokens[event.ctx.session_id] = token

    async def on_loop_end(self, event: LoopEndEvent) -> None:
        token = self._tokens.pop(event.ctx.session_id, None)
        if token is None:
            return
        self._results[event.ctx.session_id] = _ctx.collect_and_reset(token)

    def pop_components(self, session_id: str) -> list[dict]:
        """Read and clear collected components for a session. Returns [] if none."""
        return self._results.pop(session_id, [])
```

`ComponentCollectionHook` is registered at startup via `register_hook()` and also stored
on the container so the graph execution node can call `pop_components()`.

---

## Graph Propagation

`AgentState` gains a `components` field:

```python
# ze_core/orchestration/state.py
class AgentState(TypedDict):
    ...
    components: list[dict]
```

The graph node in `ze/` that calls `agent.run()` reads from the hook after execution:

```python
# In ze/ execute_agent node (or equivalent graph node):

result = await agent.run(ctx)
components = component_hook.pop_components(ctx.session_id)

return {
    "agent_result": result,
    "final_response": result.response,
    "components": components,
    ...
}
```

The output node calls:

```python
await interface.send_message(
    text=state["final_response"],
    components=state.get("components", []),
    thread_id=state["session_id"],
)
```

---

## `render_confirm` and Existing Confirmation Flow

`render_confirm` is **cosmetic in this phase**. It emits a `ConfirmComponent` descriptor
that the Flutter app renders as a modal with buttons. When the user taps a button, the
Flutter app sends a regular `message` frame (the `value` field of the tapped `ConfirmAction`
as the message text). Ze processes it as a normal inbound message.

The existing `pending_confirmation: bool` + `await_confirmation` graph pause mechanism is
unchanged. That mechanism handles cases where the graph must pause and resume (e.g. drafting
an email for review). `render_confirm` and the graph pause are two separate concerns:

| Use case | Mechanism |
|----------|-----------|
| Destructive action: "Send this email?" | `pending_confirmation` + graph pause |
| Preference prompt: "Which format?" | `render_confirm` (cosmetic) |

Whether to unify these in a future phase is an open question, deferred.

---

## Code Generation

### Approach

```
Python dataclasses (ze_components/types.py)
  → JSON schema    (docs/component-schema.json)     via scripts/generate_components.py
  → Dart @freezed  (ze-flutter/lib/src/components/)  via scripts/generate_components.py
```

### `scripts/generate_components.py`

1. Imports `COMPONENT_TYPES`, `SUB_ITEM_TYPES` from `ze_components.types`.
2. Calls `_dataclass_schema()` from `ze_components.schema` for each type.
3. Writes `docs/component-schema.json` with `$defs` per type, discriminated on `type`.
4. Emits one Dart `@freezed` class file per component type.
5. Emits `component_descriptor.dart` with a `componentFromJson()` factory dispatching on
   the `type` field.

### `Makefile` target

```makefile
generate-components:
	uv run scripts/generate_components.py
	cd packages/ze-flutter && dart run build_runner build --delete-conflicting-outputs
```

### Generated Dart shape (illustrative)

```dart
// ze-flutter/lib/src/components/table_component.dart
@freezed
class TableComponent with _$TableComponent {
  const factory TableComponent({
    required List<String> headers,
    required List<List<String>> rows,
    String? title,
    String? caption,
    @Default('table') String type,
  }) = _TableComponent;

  factory TableComponent.fromJson(Map<String, dynamic> json) =>
      _$TableComponentFromJson(json);
}
```

```dart
// ze-flutter/lib/src/components/component_descriptor.dart
ComponentDescriptor componentFromJson(Map<String, dynamic> json) =>
  switch (json['type'] as String) {
    'table'    => TableComponent.fromJson(json),
    'metric'   => MetricComponent.fromJson(json),
    'list'     => ListComponent.fromJson(json),
    'timeline' => TimelineComponent.fromJson(json),
    'progress' => ProgressComponent.fromJson(json),
    'confirm'  => ConfirmComponent.fromJson(json),
    'form'     => FormComponent.fromJson(json),
    'card'     => CardComponent.fromJson(json),
    _          => throw FormatException('Unknown component type: ${json['type']}'),
  };
```

---

## End-to-End Flow

```
Agent LLM calls render_table(headers=[...], rows=[...])
  → _wrapper(**kwargs) runs
  → TableComponent constructed
  → _ctx.append(TableComponent) → appended to ContextVar list
  → LLM receives: "Rendered table: Contacts (5 rows)"
  → LLM continues or ends turn

on_loop_end fires
  → ComponentCollectionHook.on_loop_end()
  → collect_and_reset() drains ContextVar
  → results stored: _results[session_id] = [{"type": "table", ...}]

Graph execute_agent node
  → component_hook.pop_components(session_id) → [{"type": "table", ...}]
  → AgentState["components"] = [...]

Output node
  → NativeAppInterface.send_message(text, components=[...])
  → Message saved to Postgres (components stored as JSONB)
  → WS frame: {"type": "message", "message": {..., "components": [...]}}

Flutter app
  → componentFromJson({"type": "table", ...}) → TableComponent
  → renders TableWidget below text response
```

---

## Pre-Mortem Mitigations

### T1 — LLM sends wrong key names in sub-item dicts

The LLM calls `render_list(items=[{"label": "foo"}])` (using `label` instead of `text`).
`ListItem(label="foo")` raises `TypeError`. The tool returns an error string to the LLM,
which self-corrects. In practice this loops once. **Mitigation already in spec:** the tool
description specifies required field names explicitly. Additionally `_coerce()` could be
extended with a synonym map (`label` → `text`) in a follow-up if retry loops are observed.

### T2 — `create_task` breaks ContextVar inheritance

Tools dispatched via `asyncio.create_task()` inherit a context snapshot at creation time.
Mutations from the task do not propagate back to the parent coroutine's ContextVar.
**Mitigation:** All tool calls in `_agentic_loop` are directly awaited, not dispatched via
`create_task`. This is enforced by how `call_tool()` works in `base_agent.py`. The spec
notes this invariant; if `create_task`-based tool dispatch is ever added to the harness,
the component collection mechanism must be revisited.

### T3 — `_tokens` / `_results` dicts on the hook grow unboundedly on error paths

If `on_loop_end` never fires (unhandled exception in the agent loop before the hook),
the token and result dicts accumulate entries. **Mitigation:** `pop_components()` already
removes entries. The token dict is bounded to the number of concurrent sessions (one for
Ze). Add a safety cleanup: on `ZeContainer` shutdown, assert both dicts are empty and
log a warning if not.

### T4 — Render tools registered globally conflict across tests

`@render_tool` calls `_tools[name] = ...` on import. If `ze_components.tools` is imported
in multiple test modules, the second import raises `AgentConfigError("Duplicate tool name")`.
**Mitigation:** `clear_tool_registry()` already exists for tests. Add a `clear_render_tools()`
fixture or guard in `@render_tool` that skips registration if the name is already present
in test mode. Use `TESTING=true` env var or pass `overwrite=True` to the decorator in test
context.

### T5 — `_build_render_schema` silently drops unknown type annotations

If a new sub-item type is added to a component and `_field_schema()` hits the fallback
(`return {"type": "string"}`), the LLM receives an incorrect schema fragment with no
error. **Mitigation:** Add an assertion in `build_render_schema()` that raises at import
time (not runtime) if an unsupported annotation is encountered. This surfaces schema gaps
during development, not in production.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.orchestration.tool` | `ToolSpec`, `_tools` registry — `_schema_override` field added |
| `ze_core.orchestration.hooks` | `BaseHarnessHook`, `register_hook()` — `ComponentCollectionHook` integrates here |
| `ze_core.orchestration.state.AgentState` | `components: list[dict]` field added |
| `ze_core.messages.types.Message` | `components` field (Phase 40) |
| `dataclasses` (stdlib) | `fields()`, `asdict()`, `is_dataclass()` |
| `typing` (stdlib) | `get_type_hints()`, `get_origin()`, `get_args()` |

No new third-party dependencies in `ze-components`. Dart side requires `freezed` +
`json_serializable` + `build_runner` in the Flutter package.

---

## Testing

| Test | Location |
|------|----------|
| `render_table` appends correct dict to ContextVar | `tests/components/test_tools.py` |
| `render_list` coerces `{"text": "foo"}` dict to `ListItem` | `tests/components/test_tools.py` |
| `render_list` raises `TypeError` (→ tool error string) on missing required field | `tests/components/test_tools.py` |
| `render_confirm` produces correct `ConfirmComponent` dict | `tests/components/test_tools.py` |
| `render_tool` confirmation string includes component type and item count | `tests/components/test_tools.py` |
| `begin_collection` / `collect_and_reset` round-trip collects all appends | `tests/components/test_context.py` |
| Two concurrent coroutines collect into independent lists | `tests/components/test_context.py` |
| `collect_and_reset` outside a collection context returns `[]` | `tests/components/test_context.py` |
| `build_render_schema` produces nested `items` schema for list fields | `tests/components/test_schema.py` |
| `build_render_schema` raises on unknown annotation (assertion guard) | `tests/components/test_schema.py` |
| `build_render_schema` skips `init=False` fields (no `type` in schema) | `tests/components/test_schema.py` |
| `ToolSpec.llm_schema()` uses `_schema_override` when set | `tests/orchestration/test_tool.py` |
| `ToolSpec.llm_schema()` auto-generates when `_schema_override` is None | `tests/orchestration/test_tool.py` |
| `ComponentCollectionHook.on_loop_start` sets fresh ContextVar | `tests/components/test_hook.py` |
| `ComponentCollectionHook.on_loop_end` drains ContextVar into `_results` | `tests/components/test_hook.py` |
| `pop_components` returns and removes results; second call returns `[]` | `tests/components/test_hook.py` |
| Concurrent sessions produce independent results in the hook | `tests/components/test_hook.py` |
| `asdict()` on each component type produces valid JSON-serializable dict | `tests/components/test_types.py` |
| `type` discriminator field is present in `asdict()` output | `tests/components/test_types.py` |
| `generate_components.py` script emits valid JSON schema | `tests/scripts/test_generate_components.py` |

---

## Open Questions

- [x] **Should `ze-components` be part of `ze_core`?** → **No.** Its own package with no
  ze deps, following the same pattern as `ze-browser`. Other domain packages
  (`ze-finance`, `ze-legal`, `ze-news`) can add render tools without depending on ze-core.
- [x] **One `@render_tool` per component or one generic `render_component(type, data)`?** →
  One per component. Each tool is self-describing. The LLM's tool-use training applies
  directly. A generic tool requires the LLM to know a discriminated union schema before
  using it — more failure surface.
- [x] **Where are components carried between the hook and the graph?** → On
  `ComponentCollectionHook._results`, keyed by `session_id`. The graph node calls
  `component_hook.pop_components(session_id)` after `agent.run()`. The hook instance is
  stored on the container and injected into the relevant graph node via `configurable`.
- [x] **Should `render_confirm` integrate with `await_confirmation` graph pause?** → No,
  not in this phase. `render_confirm` is cosmetic. The existing graph pause continues to
  handle confirmation-required actions. Unification is deferred.
- [ ] **Which agents should opt in to render tools?** To be decided when each agent is
  updated post-Phase 42. At minimum: research agent (tables, lists), calendar agent
  (timeline), goal agent (progress), workflow agent (progress, list). Reminder and email
  agents likely need no render tools in the first pass.
