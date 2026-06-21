# Primitive UI — Spec

> **Package:** `ze-components`, `apps/ze-web`
> **Phase:** 66
> **Status:** Done
> **Depends on:** Phase 41 ([41-component-descriptors.md](41-component-descriptors.md)), Phase 43 ([43-react-web-app.md](43-react-web-app.md))
> **Supersedes:** Phase 41 component type model (named components → primitive trees)

---

## Motivation

Phase 41 introduced *named components*: each semantic concept (table, metric, timeline…) is a
separate Python dataclass, a separate React file, and a case in `ComponentRenderer`'s switch.
Adding a new component means touching Python **and** the frontend.

This contradicts the premise of server-driven UI: the backend should be able to introduce new
UI patterns without a frontend build.

The fix is *primitive composition*. The frontend renders a small, fixed set of layout and content
primitives — a vocabulary that never grows. New semantic patterns are Python functions that compose
these primitives into trees. Zero frontend changes required.

---

## Design

### Primitive vocabulary

Nine primitive types. The frontend switch covers exactly these nine cases and never changes.

```
Layout
  col        Vertical stack of children. Variant controls surface style.
  row        Horizontal stack of children.

Content atoms
  text       Styled string — heading / subheading / body / label / caption / code.
  badge      Small coloured label — default / success / warning / error / info.
  divider    Horizontal rule.
  spacer     Blank gap.
  button     Tappable action. Emits action string back to backend as a message.
  progress   Horizontal progress bar (0.0–1.0).

Structured
  table      Header row + data rows. The one primitive that cannot be composed
             cleanly from rows/cols without sacrificing semantic alignment.
```

### Python dataclasses

```python
# ze_components/primitives.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Union

Primitive = Union[
    "Col", "Row", "Text", "Badge", "Divider",
    "Spacer", "Button", "ProgressBar", "Table",
]

@dataclass
class Col:
    children: list[Primitive]
    gap: Literal["none", "sm", "md", "lg"] = "sm"
    variant: Literal["default", "card", "section"] = "default"
    type: Literal["col"] = field(default="col", init=False)

@dataclass
class Row:
    children: list[Primitive]
    gap: Literal["none", "sm", "md", "lg"] = "sm"
    align: Literal["start", "center", "end", "between"] = "start"
    type: Literal["row"] = field(default="row", init=False)

@dataclass
class Text:
    content: str
    style: Literal["heading", "subheading", "body", "label", "caption", "code"] = "body"
    color: Literal["default", "muted", "success", "warning", "error"] = "default"
    type: Literal["text"] = field(default="text", init=False)

@dataclass
class Badge:
    label: str
    color: Literal["default", "success", "warning", "error", "info"] = "default"
    type: Literal["badge"] = field(default="badge", init=False)

@dataclass
class Divider:
    type: Literal["divider"] = field(default="divider", init=False)

@dataclass
class Spacer:
    size: Literal["sm", "md", "lg"] = "md"
    type: Literal["spacer"] = field(default="spacer", init=False)

@dataclass
class Button:
    label: str
    action: str
    style: Literal["primary", "secondary", "danger"] = "secondary"
    type: Literal["button"] = field(default="button", init=False)

@dataclass
class ProgressBar:
    value: float        # 0.0 – 1.0
    label: str | None = None
    type: Literal["progress"] = field(default="progress", init=False)

@dataclass
class Table:
    headers: list[str]
    rows: list[list[str]]
    title: str | None = None
    caption: str | None = None
    type: Literal["table"] = field(default="table", init=False)

PRIMITIVE_TYPES: list[type] = [
    Col, Row, Text, Badge, Divider, Spacer, Button, ProgressBar, Table,
]
```

### Builder helpers

Builder helpers are plain Python functions (not tools, not dataclasses). They compose primitives
into common semantic patterns. Adding a new pattern is adding one Python function.

```python
# ze_components/builders.py

from ze_components.primitives import Col, Row, Text, Badge, ProgressBar, Button, Spacer

def metric(label: str, value: str, trend: str | None = None) -> Col:
    children: list = [Text(label, style="label"), Text(value, style="heading")]
    if trend:
        children.append(Text(trend, style="caption", color="muted"))
    return Col(children, variant="card")

def stat_row(stats: list[tuple[str, str]]) -> Row:
    return Row([metric(label, value) for label, value in stats], gap="md")

def list_items(
    items: list[dict],          # {"text": str, "subtext"?: str, "status"?: str}
    title: str | None = None,
) -> Col:
    rows = []
    for item in items:
        inner = [Text(item["text"])]
        if item.get("subtext"):
            inner.append(Text(item["subtext"], style="caption", color="muted"))
        badge_color = {"done": "success", "active": "info", "error": "error"}.get(
            item.get("status", ""), "default"
        )
        row = Row([Badge(item["status"], color=badge_color), Col(inner, gap="none")]) if item.get("status") else Col(inner, gap="none")
        rows.append(row)
    if title:
        rows = [Text(title, style="subheading")] + rows
    return Col(rows, gap="sm")

def timeline(
    events: list[dict],         # {"time": str, "title": str, "description"?: str}
    title: str | None = None,
) -> Col:
    rows = []
    for e in events:
        inner = [Text(e["title"])]
        if e.get("description"):
            inner.append(Text(e["description"], style="caption", color="muted"))
        rows.append(Row([Badge(e["time"]), Col(inner, gap="none")], gap="sm"))
    if title:
        rows = [Text(title, style="subheading")] + rows
    return Col(rows, gap="md")

def progress_steps(
    title: str,
    steps: list[dict],          # {"label": str, "status": "done"|"active"|"pending"}
) -> Col:
    rows = []
    for step in steps:
        color = {"done": "success", "active": "info", "pending": "default"}[step["status"]]
        rows.append(Row([Badge(step["status"], color=color), Text(step["label"])], gap="sm", align="center"))
    return Col([Text(title, style="subheading"), Spacer("sm")] + rows, gap="sm")

def confirm_prompt(prompt: str, actions: list[dict]) -> Col:
    # actions: [{"label": str, "action": str, "style"?: str}]
    buttons = [Button(a["label"], a["action"], a.get("style", "secondary")) for a in actions]
    return Col([Text(prompt), Row(buttons, gap="sm")], gap="md", variant="card")
```

### Render tools

Render tools remain as named LLM-callable functions. They now call builder helpers and emit
`Primitive` trees. The `@render_tool` decorator and the `ContextVar` side-channel are unchanged.

```python
# ze_components/tools.py

@render_tool(description="Render structured data as a table.")
async def render_table(
    headers: list,
    rows: list,
    title: str | None = None,
    caption: str | None = None,
) -> Primitive:
    return Table(headers=headers, rows=rows, title=title, caption=caption)


@render_tool(description="Render a single highlighted metric (label + value + optional trend).")
async def render_metric(label: str, value: str, trend: str | None = None) -> Primitive:
    return builders.metric(label, value, trend)


@render_tool(description="Render a list of items with optional subtitles and status badges.")
async def render_list(items: list, title: str | None = None) -> Primitive:
    return builders.list_items(items, title)


@render_tool(description="Render events in chronological order.")
async def render_timeline(events: list, title: str | None = None) -> Primitive:
    return builders.timeline(events, title)


@render_tool(description="Render a step-by-step progress tracker.")
async def render_progress(title: str, steps: list) -> Primitive:
    return builders.progress_steps(title, steps)


@render_tool(description="Render a confirmation prompt with action buttons.")
async def render_confirm(prompt: str, actions: list) -> Primitive:
    return builders.confirm_prompt(prompt, actions)


@render_tool(description="Render a highlighted text card.")
async def render_card(body: str, title: str | None = None, style: str = "info") -> Primitive:
    variant = {"info": "default", "warning": "section", "success": "section", "error": "section"}.get(style, "default")
    children = ([Text(title, style="subheading")] if title else []) + [Text(body)]
    return Col(children, variant=variant)
```

### Frontend: recursive PrimitiveRenderer

`ComponentRenderer.tsx` is replaced by `PrimitiveRenderer.tsx`. It is recursive, not a flat
switch. The switch covers the nine fixed primitive types — no `never` exhaustiveness on a
discriminated union that grows.

```tsx
// apps/ze-web/src/components/server-driven/PrimitiveRenderer.tsx

export function PrimitiveRenderer({ node }: { node: Primitive }) {
  switch (node.type) {
    case "col":      return <ColRenderer node={node} />;
    case "row":      return <RowRenderer node={node} />;
    case "text":     return <TextRenderer node={node} />;
    case "badge":    return <BadgeRenderer node={node} />;
    case "divider":  return <hr className="border-border" />;
    case "spacer":   return <SpacerRenderer node={node} />;
    case "button":   return <ButtonRenderer node={node} />;
    case "progress": return <ProgressRenderer node={node} />;
    case "table":    return <TableRenderer node={node} />;
    default:
      // Unknown primitive from a newer backend — render nothing, don't crash.
      return null;
  }
}

function ColRenderer({ node }: { node: ColPrimitive }) {
  return (
    <div className={colClasses(node)}>
      {node.children.map((child, i) => <PrimitiveRenderer key={i} node={child} />)}
    </div>
  );
}
// … one small renderer per primitive type
```

The `default` branch returns `null` rather than asserting `never`, making the frontend
forward-compatible: a new primitive type emitted by a newer backend renders as nothing
rather than crashing.

---

## Migration from Phase 41 named components

| Phase 41 type | Phase 66 equivalent |
|---|---|
| `TableComponent` | `Table` primitive (direct) |
| `MetricComponent` | `builders.metric(label, value, trend)` → `Col` |
| `ListComponent` | `builders.list_items(items, title)` → `Col` |
| `TimelineComponent` | `builders.timeline(events, title)` → `Col` |
| `ProgressComponent` | `builders.progress_steps(title, steps)` → `Col` |
| `ConfirmComponent` | `builders.confirm_prompt(prompt, actions)` → `Col` |
| `FormComponent` | Deferred — forms need interactive input primitives (see below) |
| `CardComponent` | `Col([...], variant="card")` |
| `ChoiceGroupComponent` | `builders.confirm_prompt` + button per choice |
| `ConsentComponent` | `Col` + two buttons |
| `ConnectAccountComponent` | `Col` + button |
| `ReviewComponent` | `Table` + two buttons |
| `ConnectionsComponent` | `Col` of `Col(variant="card")` per connection |

### Interactive primitives (deferred)

`FormComponent` and similar cannot be fully replaced without interactive atom primitives
(`input`, `select`, `toggle`, `chips`). These are deferred to a follow-up phase. In the
interim, `FormComponent` can remain as a special case or be emitted as a `table` primitive
for read-only review contexts.

The deferred primitives follow the same pattern: add them to `primitives.py`, add a renderer
in `PrimitiveRenderer.tsx`, no other frontend changes required.

---

## Package changes

### `ze-components`

- Add `ze_components/primitives.py` — `Col`, `Row`, `Text`, `Badge`, `Divider`, `Spacer`, `Button`, `ProgressBar`, `Table` + `PRIMITIVE_TYPES`
- Add `ze_components/builders.py` — all builder helpers
- Update `ze_components/tools.py` — render tools return `Primitive` trees via builders
- Update `ze_components/schema.py` — `_build_render_schema` and codegen work against `PRIMITIVE_TYPES`
- Retire `ze_components/types.py` named components (or keep as deprecated shims until migration is complete)

### `apps/ze-web`

- Add `src/components/server-driven/PrimitiveRenderer.tsx` — recursive renderer
- Add one small renderer file per primitive type (9 files)
- Delete `TableComponent.tsx`, `MetricComponent.tsx`, `ListComponent.tsx`, `TimelineComponent.tsx`, `ProgressComponent.tsx`, `ConfirmComponent.tsx`, `FormComponent.tsx`, `CardComponent.tsx`, `ConnectionsComponent.tsx`
- Delete `ComponentRenderer.tsx` (replaced by `PrimitiveRenderer.tsx`)
- Regenerate `types.ts` from new `PRIMITIVE_TYPES` via `make generate-components`

---

## Adding a new component after this phase

1. Write a builder function in `ze_components/builders.py` that returns a `Primitive` tree.
2. If a named render tool is needed, add it in `ze_components/tools.py` calling the builder.
3. Run `make generate-components` to update `types.ts` (only if a new primitive was added — rare).

No React file needed. No frontend build needed unless a genuinely new primitive is introduced,
which should be rare.

---

## What does NOT change

- `ContextVar` side-channel (`ze_components/context.py`) — unchanged
- `ComponentCollectionHook` — unchanged
- `AgentState.components` field — unchanged (`list[dict]`)
- `NativeAppInterface.send_message(components=...)` — unchanged
- `@render_tool` decorator — unchanged
- How agents call render tools — unchanged

---

## Open questions

- [ ] **Interactive primitives**: Which input atom primitives are needed and in what order? Candidate: `input`, `select`, `toggle`, `chips`. Each adds one Python dataclass and one React renderer.
- [ ] **`col` variant naming**: `default | card | section` — is this enough surface variety, or should border/background be open-ended style props?
- [ ] **Button action dispatch**: Currently buttons return their `action` string as a plain chat message. A future phase may want buttons to emit structured events rather than text messages.
