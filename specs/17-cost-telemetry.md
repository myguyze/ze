# Cost Telemetry — Spec

## Purpose

Persist every LLM call's token usage and attributed cost to Postgres so Ze's
spending can be analysed by flow type, agent, model, and time period. The
instrumentation layer must be invisible to callers — adding a new agent or
proactive feature requires zero extra work for basic attribution, and at most
one line for new flow types.

## Design Principle

`OpenRouterClient` is the single chokepoint for every LLM call. Injecting a
`CostTracker` there is sufficient to capture all usage. Attribution context
(which flow triggered the call, which agent is running) propagates through the
async call chain via a Python `ContextVar` — set once at the flow entry point,
read automatically inside the tracker.

## New Module: `ze/telemetry/`

### `ze/telemetry/types.py`

```python
from dataclasses import dataclass

@dataclass
class CostRecord:
    agent: str
    flow_type: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    session_id: str | None
    cost_usd: float | None       # always None at write time; backfilled by CostReconciler
    generation_id: str | None    # OpenRouter generation ID for reconciliation
```

### `ze/telemetry/context.py`

```python
from contextvars import ContextVar
from dataclasses import dataclass, replace

@dataclass(frozen=True)
class CostContext:
    flow_type: str
    agent: str
    session_id: str | None = None

_CTX: ContextVar[CostContext | None] = ContextVar("ze_cost_ctx", default=None)

def set_flow_context(flow_type: str, session_id: str | None = None) -> None:
    current = _CTX.get()
    if current is not None:
        _CTX.set(replace(current, flow_type=flow_type, session_id=session_id))
    else:
        _CTX.set(CostContext(flow_type=flow_type, agent="unknown", session_id=session_id))

def set_agent_context(agent: str) -> None:
    current = _CTX.get()
    if current is not None:
        _CTX.set(replace(current, agent=agent))

def get_cost_context() -> CostContext:
    return _CTX.get() or CostContext(flow_type="unknown", agent="unknown")
```

### `ze/telemetry/tracker.py`

Records each call inline (fire-and-forget). `cost_usd` is always written as `NULL`
here — the reconciler fills it in asynchronously.

```python
class CostTracker:
    def __init__(self, pool) -> None: ...

    def record(self, model, prompt_tokens, completion_tokens,
               total_tokens, duration_ms, generation_id=None) -> None:
        """Schedules a DB write without blocking the caller. cost_usd left NULL."""
```

### `ze/telemetry/reconciler.py`

Periodic job that backfills `cost_usd` by calling OpenRouter's generation stats
endpoint for rows that have a `generation_id` but no `cost_usd` yet. Waits 2
minutes after creation before fetching (OpenRouter may lag). Processes up to 50
rows per run.

```python
class CostReconciler:
    def __init__(self, pool, sdk) -> None: ...  # sdk = OpenRouterClient._sdk

    async def run(self) -> None:
        """Fetches actual cost from GET /api/v1/generation?id=<id> and updates rows."""
```

Scheduled every 15 minutes via `WorkflowScheduler` (job_id: `cost_reconciliation`).

## DB Table: `llm_cost_log` (Migration 008)

```sql
CREATE TABLE llm_cost_log (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        TEXT,
    agent             TEXT        NOT NULL,
    flow_type         TEXT        NOT NULL,
    model             TEXT        NOT NULL,
    prompt_tokens     INT         NOT NULL,
    completion_tokens INT         NOT NULL,
    total_tokens      INT         NOT NULL,
    cost_usd          NUMERIC(12,8),   -- NULL until CostReconciler backfills it
    duration_ms       INT         NOT NULL,
    generation_id     TEXT,            -- OpenRouter ID used by CostReconciler
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX llm_cost_log_created_idx  ON llm_cost_log (created_at DESC);
CREATE INDEX llm_cost_log_flow_idx     ON llm_cost_log (flow_type, created_at DESC);
CREATE INDEX llm_cost_log_agent_idx    ON llm_cost_log (agent, created_at DESC);
CREATE INDEX llm_cost_log_session_idx  ON llm_cost_log (session_id) WHERE session_id IS NOT NULL;
```

## OpenRouterClient Changes

- Accept `cost_tracker: CostTracker | None = None` in `__init__`.
- In `complete()`: after extracting `usage`, call `self._cost_tracker.record(...)`.
- In `stream()`: capture the usage field from the final SSE chunk (currently
  discarded). OpenRouter sends a `usage` object on the last non-`[DONE]` chunk
  when `include_usage: true` is set (or on the `[DONE]` chunk itself). Add
  `"stream_options": {"include_usage": true}` to streaming requests. Accumulate
  tokens across chunks; call `tracker.record()` after the stream closes.

## Attribution Instrumentation

Agent context is set in `ze/orchestration/nodes/execution.py:_run_with_timeout()`
before every agent runs — all existing and future agents are covered automatically.
Orchestration-layer LLM calls (synthesis, workflow verify, etc.) set their own
agent label at the call site.

| Module | What is set |
|--------|-------------|
| `ze/telegram/bot.py` — message handler | `set_flow_context("user_message", str(chat_id))` |
| `ze/workflow/scheduler.py` — `_run_workflow()` | `set_flow_context("workflow_execution", session_id)` |
| `ze/proactive/insights.py` — `run()` | `set_flow_context("insight_generation")` + `set_agent_context("insights")` |
| `ze/proactive/reminders.py` — `sync()` | `set_flow_context("calendar_sync")` + `set_agent_context("reminders")` |
| `ze/memory/consolidator.py` — `run()` | `set_flow_context("memory_consolidation")` + `set_agent_context("memory_consolidation")` |
| `ze/orchestration/nodes/execution.py` — `_run_with_timeout()` | `set_agent_context(agent_name)` |
| `ze/orchestration/nodes/memory.py` — `synthesize()` | `set_agent_context("synthesis")` |
| `ze/orchestration/nodes/routing.py` — `plan_sequential()` | `set_agent_context("workflow_planner")` |
| `ze/orchestration/nodes/workflow.py` — `verify_step()` | `set_agent_context("workflow_verify")` |
| `ze/orchestration/nodes/workflow.py` — `workflow_synthesize()` | `set_agent_context("workflow_synthesize")` |
| `ze/orchestration/nodes/context.py` — `fetch_context()` | `set_agent_context("memory_store")` |
| `ze/routing/router.py` — haiku fallback | `set_agent_context("router")` |

## Cost Source

`cost_usd` is sourced exclusively from `GET /api/v1/generation?id=<generation_id>`
(OpenRouter's generation stats endpoint, `GetGenerationData.total_cost`). No local
pricing table is maintained. `CostReconciler` runs every 15 minutes and backfills
all rows older than 2 minutes that have a `generation_id` but no `cost_usd`.

## REST Endpoint: `GET /costs/summary`

Route in `ze/api/routes/costs.py`, mounted at `/costs`.

### Query params

| Param | Default | Description |
|-------|---------|-------------|
| `days` | 30 | Lookback window |
| `group_by` | `flow_type` | `flow_type` \| `agent` \| `model` \| `session_id` |

Returns a JSON object with `total_calls`, `total_tokens`, `total_cost_usd`, and
a `buckets` list grouped by the chosen dimension, ordered by `total_tokens` DESC.
`cost_usd` is `null` for rows not yet reconciled (typically the last ~15 minutes).

## Container Changes

`CostTracker(pool)` and `CostReconciler(pool, sdk=openrouter_client._sdk)` are
both constructed in `build_container()`. `CostTracker` is injected into
`OpenRouterClient`. `CostReconciler.run` is scheduled every 15 minutes via
`WorkflowScheduler` (job_id: `cost_reconciliation`).

## Testing

- `CostTracker.record()`: mock `asyncio.create_task`; assert `_write` is
  scheduled with the correct `CostRecord` fields.
- Context propagation: verify that `set_flow_context` + `set_agent_context` are
  visible inside a spawned coroutine.
- `OpenRouterClient.complete()` with a mock tracker: assert `tracker.record()`
  is called with the right token counts and `generation_id`.
- `GET /costs/summary`: mock DB, assert grouping logic.

## Out of Scope

- Real-time cost alerting / budget enforcement.
- Per-user or per-conversation cost attribution (single-user system).
- Retroactive backfill of historical calls (start tracking from deploy date).
