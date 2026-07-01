# Phase 98 — Workflow Run Chat

**Status:** Implementing  
**Scope:** ze-web (frontend); ze-api schema + ze-core orchestration (backend context injection)

---

## Problem

When a workflow run fails or produces unexpected output, the user has to switch to the main chat, mentally reconstruct which run they were looking at, and re-explain it to Ze. There is no quick path from "I see this run" to "let me ask Ze about it."

---

## Solution

A **"Chat about this"** trigger on each execution row in the workflow detail run history. One click opens the ephemeral context overlay pre-primed with a context brief about that specific run. Ze immediately knows:

- Which workflow and run the user is asking about
- Its status, duration, step count, and error (if any)
- Where to look for more detail (`list_workflow_executions` tool)

No copy-pasting IDs. No re-explaining. The user types their actual question.

---

## Surface

```
Run History                          (SectionPanel, right column)
├── Completed · Jul 1, 20:20  263s   ← row
│    ✔ 5 steps                [💬]   ← chat icon appears on hover / always visible
├── Failed    · Jul 1, 20:02   66s
│    ✘ 2 steps                [💬]
```

Clicking `[💬]`:
1. Selects that execution (populates the Steps panel — existing behaviour)
2. Opens the context overlay with the input pre-filled with a context brief
3. Overlay header shows `Ze · [Workflow name] — run [date]` instead of the generic screen label

The user hits Enter (or edits the brief first) and Ze responds immediately with run-specific knowledge.

---

## Frontend changes

### `overlay-store.ts`

Add `prefillMessage?: string` to store state.  
Add `openForExecution(params)` action that sets `open`, `screen`, `entityId`, and `prefillMessage` atomically.

```ts
openForExecution: (params: {
  screen: string;
  entityId?: string;
  prefillMessage: string;
}) => void
```

### `ContextOverlay.tsx`

Read `prefillMessage` from store.  
Initialise `input` state to `prefillMessage` when the overlay transitions to open (via `useEffect` on `open` + `prefillMessage`).  
Clear the store's `prefillMessage` after consuming it (so re-opens start empty).

### `WorkflowExecutionsList.tsx`

Accept a `workflowName: string` prop.  
Each `ExecutionRow` gets an `onChat` callback.  
A `MessageCircle` icon button (`w-3.5 h-3.5`, `text-smoke hover:text-white`) appears at the end of the row — visible on hover (`group-hover:opacity-100 opacity-0`) on desktop, always-visible on touch.

On `onChat` click: call `openForExecution` with a pre-built context brief and `e.stopPropagation()` so the row selection click doesn't also fire.

Context brief template:
```
Tell me about the "{workflowName}" workflow run from {date}. It {completed/failed} in {duration} with {stepCount} steps{: error message if any}.
```

### `WorkflowDetailPage.tsx`

Pass `workflowName={detail.name}` and an `onChat` handler to `WorkflowExecutionsList`.  
The `onChat` handler also calls `handleSelectExecution(ex)` so the steps panel updates alongside the overlay.

---

## Backend changes (context injection)

### `WsScreenContext` (ze-api `schemas.py`)

```python
class WsScreenContext(BaseModel):
    screen: str
    goal_id: str | None = None
    workflow_id: str | None = None
    execution_id: str | None = None
```

### `AgentContext` (ze-agents `types.py`)

Add runtime-only field (never checkpointed):

```python
screen_context_note: str | None = field(default=None, repr=False)
```

### `fetch_context` node (ze-core `orchestration/nodes/context.py`)

After building `agent_context`, read `screen_context` from `config["configurable"]`:

```python
screen_ctx = config["configurable"].get("screen_context") or {}
workflow_id = screen_ctx.get("workflow_id")
execution_id = screen_ctx.get("execution_id")

if workflow_id and (wf_store := config["configurable"].get("workflow_store")):
    try:
        wf = await wf_store.get(UUID(workflow_id))
        if wf:
            executions = await wf_store.list_executions(wf.id, limit=20)
            ex = next((e for e in executions if str(e.id) == execution_id), None) if execution_id else None
            note = _build_screen_context_note(wf, ex)
            agent_context.screen_context_note = note
    except Exception:
        pass  # best-effort; never block the turn
```

```python
def _build_screen_context_note(wf, ex) -> str:
    lines = [f"[Screen context: user is viewing workflow '{wf.name}']"]
    if ex:
        duration = ...  # computed from started_at / completed_at
        lines.append(f"Run: status={ex.status}, steps={len(ex.step_results)}, duration={duration}")
        if ex.error:
            lines.append(f"Error: {ex.error}")
    return "\n".join(lines)
```

Also inject into `routing_hints` so the embedding router pins to WorkflowAgent without LLM fallback:

```python
routing_hint_addition = f"[Viewing workflow: '{wf.name}']"
# merge with existing routing_hints in state via return value
```

Wait — `fetch_context` doesn't set `routing_hints` (that's the pre-route node's job). So just set `agent_context.screen_context_note`; routing stays natural since the prefill message mentions the workflow by name.

### `BaseAgent._build_system_prompt` (ze-agents `base_agent.py`)

Prepend `ctx.screen_context_note` before the agent instructions when it is set:

```python
if ctx.screen_context_note:
    rendered = f"{ctx.screen_context_note}\n\n{rendered}"
```

---

## Rollout

**Phase 98a (this PR):**
- Frontend: overlay store + prefill + chat buttons in execution rows
- Backend schema: `WsScreenContext` extended (no consumers yet; field is ignored)

**Phase 98b (follow-up):**
- Backend: `AgentContext.screen_context_note` field
- `fetch_context` node: context injection from `workflow_store`
- `BaseAgent._build_system_prompt`: inject the note
- Tests for the context note builder

The frontend UX is complete and usable after 98a — Ze understands from the prefilled message which run is being discussed. The backend wiring in 98b makes Ze aware even if the user immediately changes the topic or erases the prefill.

---

## Out of scope

- Saving workflow-run chat history (stays ephemeral; use the main chat for persistent conversations)
- "Chat about this workflow" (without a specific run) — can be done via existing FloatingButton with `screen="workflow"`
- Context injection for goal runs (same pattern, different entity; future phase)
