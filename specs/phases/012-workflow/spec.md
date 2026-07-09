# Phase 4 — Workflow System Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| WorkflowStore — CRUD | ✅ Done |
| WorkflowPlanner — NL → step list + schedule | ✅ Done |
| WorkflowScheduler — APScheduler + Postgres persistence | ✅ Done |
| WorkflowManagerAgent — user-facing CRUD + trigger | ✅ Done |
| Workflow graph — loop execution, step verification | ✅ Done |
| Dynamic planning — sequential plan approval flow | ✅ Done |
| Migration 003 — workflows + workflow_executions tables | ✅ Done |
| REST API — workflow endpoints | ✅ Done |

---

## Purpose

Add recurring, stored, and dynamically-planned multi-step task execution to Ze.
Workflows are sequences of steps executed sequentially by the existing orchestration
graph — agents remain peers, none orchestrates another. The `WorkflowManagerAgent`
handles user-facing lifecycle management (create, list, enable, disable, delete,
trigger). The graph handles execution.

---

## Out of Scope

- Memory consolidation (dedup, expiry, summarisation) — deferred to Phase 5.
- Multi-user workflow sharing.
- Step parallelism within a workflow (all steps are sequential).
- External webhook triggers (Phase 5 or later).

---

## Workflow Modes

Three modes, all using the same underlying execution path:

| Mode | Description |
|------|-------------|
| **Scheduled** | User creates a named workflow with a cron schedule. APScheduler fires it automatically. Results pushed via Telegram. |
| **On-demand** | User triggers a stored workflow by name: "run my morning briefing". |
| **Dynamic plan** | For complex multi-step requests with sequential dependencies, Ze generates a plan at runtime, shows it for approval if any step is high-risk, then executes without storing. |

---

## Repository Layout

```
ze/
├── workflow/                  # Shared module — store, types, planner, scheduler
│   ├── __init__.py
│   ├── types.py               # Workflow, WorkflowStep, WorkflowExecution, StepResult
│   ├── store.py               # WorkflowStore — asyncpg CRUD
│   ├── planner.py             # WorkflowPlanner — NL → step list + cron expression
│   └── scheduler.py           # WorkflowScheduler — APScheduler, Postgres-backed
├── agents/
│   └── workflow/
│       ├── __init__.py
│       ├── agent.py           # WorkflowManagerAgent + @register("workflow")
│       └── tools.py           # create_workflow, list_workflows, …
└── orchestration/
    └── nodes/
        └── workflow.py        # load_workflow_step, verify_step, workflow_synthesize
```

---

## Data Structures

`ze/workflow/types.py`

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

@dataclass
class WorkflowStep:
    task: str                   # natural-language task passed to embed_route
    agent_hint: str | None      # optional routing hint; embed_route may ignore
    verify: str | None          # natural-language criteria checked by verify_step

@dataclass
class Workflow:
    id: UUID
    name: str
    description: str
    steps: list[WorkflowStep]
    schedule: str | None        # cron expression (5-field), None = on-demand only
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

@dataclass
class StepResult:
    step_index: int
    task: str
    output: str
    success: bool
    error: str | None
    duration_ms: int

@dataclass
class WorkflowExecution:
    id: UUID
    workflow_id: UUID | None    # None for dynamic-plan executions
    status: str                 # pending | running | completed | failed
    step_results: list[StepResult]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
```

---

## Database Schema

Migration `migrations/versions/003_workflows.py`.

```sql
CREATE TABLE workflows (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    steps       JSONB NOT NULL,         -- serialised list[WorkflowStep]
    schedule    TEXT,                   -- cron expression or NULL
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE workflow_executions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id  UUID REFERENCES workflows(id) ON DELETE CASCADE,  -- NULL for dynamic plans
    status       TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    step_results JSONB NOT NULL DEFAULT '[]',
    error        TEXT,
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON workflow_executions (workflow_id, created_at DESC);
```

---

## WorkflowStore

`ze/workflow/store.py`

```python
class WorkflowStore:
    def __init__(self, db_pool: asyncpg.Pool): ...

    async def create(self, workflow: Workflow) -> UUID: ...
    async def get(self, workflow_id: UUID) -> Workflow | None: ...
    async def get_by_name(self, name: str) -> Workflow | None: ...
    async def list_all(self) -> list[Workflow]: ...
    async def list_enabled_scheduled(self) -> list[Workflow]: ...  # enabled=True, schedule IS NOT NULL
    async def set_enabled(self, workflow_id: UUID, enabled: bool) -> None: ...
    async def delete(self, workflow_id: UUID) -> None: ...
    async def update_run_timestamps(
        self,
        workflow_id: UUID,
        last_run_at: datetime,
        next_run_at: datetime | None,
    ) -> None: ...

    async def start_execution(self, workflow_id: UUID | None) -> UUID: ...  # returns execution_id
    async def record_step(self, execution_id: UUID, result: StepResult) -> None: ...
    async def finish_execution(
        self,
        execution_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None: ...
```

`steps` is stored as a JSONB array of dicts. Serialise `WorkflowStep` to/from dict
at the store boundary — no ORM, no Pydantic.

---

## WorkflowPlanner

`ze/workflow/planner.py`

A thin component — two LLM calls, no tool use.

```python
class WorkflowPlanner:
    def __init__(self, openrouter_client: OpenRouterClient, settings: Settings): ...

    async def plan(self, description: str) -> list[WorkflowStep]:
        """
        Parse a natural-language workflow description into an ordered step list.
        Returns at least one step. Raises WorkflowPlanError if the LLM cannot
        produce a coherent plan.
        """

    async def extract_schedule(self, description: str) -> str | None:
        """
        Extract a cron expression from a natural-language schedule description.
        Returns None if no schedule is implied.
        Examples:
          "every Monday at 8am"       → "0 8 * * 1"
          "every day at noon"         → "0 12 * * *"
          "on demand"                 → None
        """
```

Both calls use `claude-haiku-4-5` (fast, cheap). System prompt instructs the model
to output structured JSON only. Parse with `json.loads` — raise `WorkflowPlanError`
on malformed output.

`plan()` prompt contract: return a JSON array of objects:
```json
[
  {"task": "...", "agent_hint": "research", "verify": "Output contains at least 3 recent AI developments"},
  {"task": "...", "agent_hint": null, "verify": null}
]
```

`extract_schedule()` prompt contract: return a JSON object:
```json
{"cron": "0 8 * * 1"}
```
or `{"cron": null}` if on-demand.

---

## WorkflowScheduler

`ze/workflow/scheduler.py`

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

class WorkflowScheduler:
    def __init__(
        self,
        workflow_store: WorkflowStore,
        graph,                          # compiled LangGraph workflow graph
        settings: Settings,
    ): ...

    async def start(self) -> None:
        """Load all enabled scheduled workflows from Postgres, schedule them."""

    async def stop(self) -> None:
        """Shut down APScheduler gracefully."""

    async def add_workflow(self, workflow: Workflow) -> None:
        """Add or replace a job for this workflow. No-op if no schedule."""

    async def remove_workflow(self, workflow_id: UUID) -> None:
        """Remove APScheduler job. No-op if not scheduled."""

    async def trigger_now(self, workflow_id: UUID) -> None:
        """Run immediately, outside the normal schedule."""

    async def _run_workflow(self, workflow_id: UUID) -> None:
        """
        Called by APScheduler. Loads workflow from store, invokes the workflow
        graph, updates last_run_at and next_run_at.
        """
```

APScheduler job IDs are `str(workflow_id)`. On restart, `start()` calls
`list_enabled_scheduled()` and reschedules all active workflows — APScheduler holds
no persistent state of its own.

`next_run_at` in Postgres is computed from the cron expression using
`CronTrigger.from_crontab(schedule).get_next_fire_time(None, datetime.now(tz=UTC))`.
Update it after each run.

---

## Workflow Graph

A **separate** compiled LangGraph graph for workflow execution. Reuses the same node
functions as the main graph (`embed_route`, `fetch_context`, `capability_check`,
`execute_tool`, `await_confirmation`) but with a different topology that loops.

### AgentState additions

```python
# ── Workflow ──────────────────────────────────────────────────────────────
workflow_id: UUID | None             # None for dynamic-plan executions
workflow_execution_id: UUID | None
workflow_steps: list[WorkflowStep] | None
current_step_index: int              # default 0
workflow_step_results: list[StepResult]  # accumulated across steps
```

Add to `ze/orchestration/state.py`. These fields are always `None` / 0 / [] in
normal (non-workflow) graph invocations — the main graph never sets them.

### New Nodes — `ze/orchestration/nodes/workflow.py`

#### `load_workflow_step`

```
Input:  workflow_steps, current_step_index
Output: prompt (set to step.task), envelope=None, memory_context=None,
        agent_context=None, gate_decision=None, agent_result=None
```

Resets all per-step state fields and sets `prompt` to the current step's task.
The graph then routes normally via `embed_route`.

#### `verify_step`

```
Input:  agent_result, workflow_steps[current_step_index], workflow_execution_id
Output: workflow_step_results (appended), current_step_index (incremented)
```

Verification logic (in order):

1. **Tool success check** — any `ToolCall.success=False` → step failed.
2. **Non-empty output check** — `agent_result.output` empty → step failed.
3. **Criteria check** — if `step.verify` is not None, call Haiku with:
   - the step output
   - the verify criteria string
   - return `{"pass": true/false, "reason": "..."}`.
   If Haiku call fails, log warning and treat as passed (non-blocking).

On failure: set `StepResult.success=False`, fire `WorkflowStore.record_step()`,
then route to `workflow_failed`.

On success: fire `WorkflowStore.record_step()` (non-blocking via `create_task`),
increment `current_step_index`, route to next step or `workflow_synthesize`.

#### `workflow_synthesize`

```
Input:  workflow_step_results, workflow_id
Output: final_response
```

Calls Haiku to merge all step outputs into a concise summary. Calls
`WorkflowStore.finish_execution(status="completed")`. Sets `final_response`.

#### `workflow_failed`

```
Input:  workflow_step_results, current_step_index, error
Output: final_response (failure notice)
```

Calls `WorkflowStore.finish_execution(status="failed", error=...)`. Sets
`final_response` to a human-readable failure message including which step failed.

### Workflow Graph Assembly

`ze/orchestration/workflow_graph.py`

```python
def build_workflow_graph(checkpointer: AsyncPostgresSaver) -> CompiledGraph:
    builder = StateGraph(AgentState)

    # Reused nodes
    builder.add_node("embed_route",        nodes.routing.embed_route)
    builder.add_node("fetch_context",      nodes.context.fetch_context)
    builder.add_node("capability_check",   nodes.execution.capability_check)
    builder.add_node("execute_tool",       nodes.execution.execute_tool)
    builder.add_node("await_confirmation", nodes.confirmation.await_confirmation)
    builder.add_node("write_memory",       nodes.memory.write_memory)

    # Workflow-specific nodes
    builder.add_node("load_workflow_step", nodes.workflow.load_workflow_step)
    builder.add_node("verify_step",        nodes.workflow.verify_step)
    builder.add_node("workflow_synthesize",nodes.workflow.workflow_synthesize)
    builder.add_node("workflow_failed",    nodes.workflow.workflow_failed)

    builder.set_entry_point("load_workflow_step")

    builder.add_edge("load_workflow_step", "embed_route")
    builder.add_edge("embed_route",        "fetch_context")
    builder.add_edge("fetch_context",      "capability_check")
    builder.add_conditional_edges("capability_check", edges.after_capability_check_workflow)
    builder.add_edge("execute_tool",       "write_memory")
    builder.add_edge("write_memory",       "verify_step")
    builder.add_conditional_edges("verify_step", edges.after_verify_step)
    builder.add_edge("await_confirmation", "execute_tool")   # resume after user confirms
    builder.add_edge("workflow_synthesize", END)
    builder.add_edge("workflow_failed",    END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
```

### Conditional Edges

```python
def after_capability_check_workflow(state: AgentState) -> str:
    decision = state["gate_decision"]
    match decision:
        case GateDecision.EXECUTE:            return "execute_tool"
        case GateDecision.DRAFT:              return "execute_tool"  # workflows always execute
        case GateDecision.AWAIT_CONFIRMATION: return "await_confirmation"
        case GateDecision.BLOCKED:            return "workflow_failed"

def after_verify_step(state: AgentState) -> str:
    last = state["workflow_step_results"][-1]
    if not last.success:
        return "workflow_failed"
    if state["current_step_index"] >= len(state["workflow_steps"]):
        return "workflow_synthesize"
    return "load_workflow_step"
```

### Thread ID Convention

Workflow graph invocations use `thread_id = str(workflow_execution_id)`. This means
`await_confirmation` interrupts are tied to a specific execution, not a Telegram
session. The Telegram bot maps the confirmation callback to the execution's
`thread_id` to resume the graph.

---

## WorkflowManagerAgent

`ze/agents/workflow/agent.py`

```python
_AGENT_INSTRUCTIONS = """
You are Ze's workflow manager. You create, list, enable, disable, delete, and
trigger stored workflows. A workflow is a named sequence of tasks that Ze executes
in order. Workflows can run on a cron schedule or on demand.

When the user asks to create a workflow, extract:
  1. A short, memorable name (snake_case).
  2. A description of what the workflow does.
  3. The schedule, if any (natural language — you will not compute the cron yourself).

Use your tools directly. Do not narrate tool calls.
"""
```

**Tools** (`ze/agents/workflow/tools.py`):

| Tool | Description |
|------|-------------|
| `create_workflow(name, description, steps_description, schedule_description)` | Calls `WorkflowPlanner.plan()` + `extract_schedule()`, stores via `WorkflowStore`, registers with `WorkflowScheduler`. |
| `list_workflows()` | Returns all workflows with name, description, schedule, enabled, last_run_at. |
| `get_workflow(name_or_id)` | Returns full workflow detail including step list. |
| `enable_workflow(name_or_id)` | Sets `enabled=True`, re-registers schedule. |
| `disable_workflow(name_or_id)` | Sets `enabled=False`, removes from scheduler. |
| `delete_workflow(name_or_id)` | Removes from Postgres + scheduler. |
| `trigger_workflow(name_or_id)` | Calls `WorkflowScheduler.trigger_now()`. Returns "triggered". |

**Agent config** (`config/agents/workflow.yaml`):

```yaml
enabled: true
description: |
  Manages stored workflows and recurring scheduled tasks. Use when the user
  wants to create, list, enable, disable, delete, or manually run a named
  workflow or recurring automated task.
model: anthropic/claude-sonnet-4-5
timeout: 30
```

**Capability config** (`config/capabilities.yaml` additions):

```yaml
workflow.create:  confirm
workflow.read:    autonomous
workflow.update:  confirm
workflow.delete:  confirm
workflow.execute: confirm
```

---

## Dynamic Planning (Mode 3)

For complex user requests with sequential step dependencies, the orchestration layer
generates a plan and executes it without storing a workflow.

Detection: the `decompose` node in the main graph already handles compound tasks by
fanning out parallel subtasks. Dynamic planning is separate: it handles requests
where step N's output feeds step N+1. The distinguishing signal is that
`WorkflowPlanner.plan()` is called when the LLM in `decompose` indicates sequential
dependencies (vs. independent parallel subtasks).

### Flow

```
User: "Research the latest AI news, then draft me an email summary, then add a
       calendar reminder to review it Friday"

decompose → detects sequential dependencies → calls WorkflowPlanner.plan()
          → produces 3-step plan
          → capability_check each step:
              step 1 (research.read)   → EXECUTE       (no approval needed)
              step 2 (email.create)    → DRAFT_ONLY     ← high-risk
              step 3 (calendar.create) → CONFIRM        ← high-risk
          → any high-risk steps? → yes
          → format plan summary with flagged steps → await_confirmation
          → user approves → execute via workflow graph (workflow_id=None)
          → results synthesised and returned
```

Plan approval message format (Telegram):

```
Ze will run 3 steps:
  1. Research latest AI news
  2. ⚠️ Draft email (requires approval)
  3. ⚠️ Add calendar reminder (requires confirmation)

Proceed?  [Yes]  [No]
```

If the user says No, the workflow is abandoned and Ze asks what they'd like to
change. If Yes, the workflow graph executes with `workflow_id=None`.

---

## Errors and Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Planner returns zero steps | Raise `WorkflowPlanError`, tell user Ze couldn't parse the workflow |
| `extract_schedule` returns invalid cron | Raise `WorkflowPlanError`, ask user to clarify the schedule |
| Step tool call fails | `verify_step` fails the step → `workflow_failed` → Telegram notification |
| Haiku verification call fails | Log warning, treat step as passed |
| Scheduled workflow fires but is disabled | `_run_workflow` checks `enabled` before invoking graph; no-op if disabled |
| Confirmation timeout during workflow execution | Existing `CONFIRM_TIMEOUT_SECONDS` applies; graph abandons thread, `WorkflowStore.finish_execution(status="failed")` |
| APScheduler not started (test env) | `WorkflowScheduler.start()` is a no-op when `settings.scheduler_enabled=False` |
| Workflow deleted while running | `ON DELETE CASCADE` removes executions; in-flight graph runs to completion or fails gracefully |

---

## New Dependencies

```toml
"apscheduler>=3.10"   # AsyncIOScheduler, CronTrigger
```

Add to `pyproject.toml` `[project.dependencies]`.

---

## Container Wiring

`ze/container.py` additions (in dependency order):

```python
workflow_store     = WorkflowStore(db_pool=db_pool)
workflow_planner   = WorkflowPlanner(openrouter_client=openrouter_client, settings=settings)
workflow_scheduler = WorkflowScheduler(workflow_store=workflow_store, graph=workflow_graph, settings=settings)
workflow_agent     = WorkflowManagerAgent(
    workflow_store=workflow_store,
    workflow_planner=workflow_planner,
    workflow_scheduler=workflow_scheduler,
    openrouter_client=openrouter_client,
    settings=settings,
)
```

`WorkflowScheduler.start()` is called in the FastAPI lifespan **after** the workflow
graph is compiled. `WorkflowScheduler.stop()` is called in lifespan teardown.

---

## REST API

New routes in `ze/api/workflows.py` (mounted at `/workflows`):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/workflows` | List all workflows |
| `GET` | `/workflows/{id}` | Get workflow detail + steps |
| `GET` | `/workflows/{id}/executions` | List executions (newest first, limit 20) |
| `POST` | `/workflows/{id}/trigger` | Trigger immediate execution |

All routes require `X-API-Key` header (same as existing routes). All must declare
`response_model`, `summary`, and `description` per the API spec (spec-07).

---

## Settings Additions

`ze/settings.py`:

```python
scheduler_enabled: bool = True   # set False in test env to skip APScheduler
workflow_verify_model: str = "anthropic/claude-haiku-4-5"
workflow_plan_model: str = "anthropic/claude-haiku-4-5"
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze.workflow.store` | `WorkflowStore` |
| `ze.workflow.planner` | `WorkflowPlanner` |
| `ze.workflow.scheduler` | `WorkflowScheduler` |
| `ze.workflow.types` | `Workflow`, `WorkflowStep`, `StepResult`, `WorkflowExecution` |
| `ze.orchestration.nodes.*` | Reused node functions in workflow graph |
| `ze.errors` | `WorkflowPlanError`, `WorkflowExecutionError` |
| `ze.openrouter.client` | Planner + verification LLM calls |
| `ze.db` | asyncpg pool |
| `ze.settings` | Scheduler toggle, model config |

Add to `ze/errors.py`:
- `WorkflowPlanError(ZeError)` — planner failed to produce a valid plan
- `WorkflowExecutionError(ZeError)` — step execution failed unrecoverably

---

## Open Questions

All resolved.
