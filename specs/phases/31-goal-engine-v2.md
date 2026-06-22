# Goal Engine v2 — Spec

> **Package:** `ze_personal`, `ze_core` (migration only)
> **Phase:** 23
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| Milestone context injection | ✅ Done |
| Execution trace store (migration + store) | ✅ Done |
| Execution trace exposure (tool) | ✅ Done |
| Adaptive replanning trigger | ✅ Done |
| Enriched gate narrative | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

The Phase 19 goal engine executes milestones autonomously but each milestone fires blind — the
executing agent has no knowledge of the goal it serves, what prior milestones found, or what the
user has corrected. Failures are silently skipped rather than recovered from. Verification gate
messages contain 150-character truncations of milestone outputs, giving the user barely enough
information to make a decision.

This phase makes the goal execution loop contextual, observable, and self-correcting:

- Every milestone runs with full goal context and a summarized view of prior work.
- Every tool call during execution is persisted for later inspection.
- Consecutive milestone failures trigger automatic replanning rather than silent skip-ahead.
- Verification gate messages contain a synthesized narrative rather than truncated bullet points.
- Reusable procedures discovered during the goal are fed back into later milestones and
  replans for the same goal before they are promoted to global memory.

---

## Responsibilities

- Inject goal context (objective, success condition, learnings, prior outputs) into every milestone prompt before execution.
- Persist execution traces (tool calls) for every milestone run.
- Expose traces to the user via the goal agent's tool interface.
- Detect consecutive milestone failures and trigger `GoalPlanner.replan_remaining` automatically.
- Synthesize a narrative summary at gate fire time via an LLM call.
- Extract provisional reusable procedures from milestone clusters during active goals and
  make them available to subsequent milestones and replans inside the same goal.
- Promote stable procedures to `MemoryStore.propose_procedure()` on completion so future
  goals can reuse them too.

---

## Out of Scope

- **Conversational steering** — mid-execution redirects via free-form Telegram messages (Phase 24).
- **Weekly progress narrative job** — a proactive scheduled digest of goal activity (Phase 24).
- **Context window budget manager** — summarizing old milestone outputs for very long goals. The
  truncation strategy in this phase (last 3 full, older capped at 100 chars) is sufficient for
  goals up to ~15 milestones.
- **Parallel milestone execution** — goals with independent milestone sub-sequences running
  concurrently. Out of scope indefinitely until a concrete use case warrants the complexity.

---

## Module Location

No new top-level modules. All changes are within existing files plus one new migration and one new
store method set.

```
packages/ze-core/
  ze_core/
    migrations/versions/
      006_goal_execution_traces.py     ← new migration

packages/ze-personal/
  ze_personal/
    goals/
      types.py                         ← add ExecutionTrace dataclass
      store.py                         ← add trace Protocol methods
      postgres.py                      ← implement trace store methods
      executor.py                      ← context injection, adaptive replan, enriched gate
      planner.py                       ← add synthesize_gate_narrative()
    agents/goals/
      tools.py                         ← add get_milestone_trace tool
      agent.py                         ← add get_milestone_trace to tools list
```

---

## Feature 1: Milestone Context Injection

### Problem

`_execute_milestone` constructs an `AgentContext` with only `session_id`,
`prompt=milestone.description`, `intent`, and `gate_decision`. The executing agent receives no
information about the goal it serves, what earlier milestones produced, or what the user has
corrected via gate redirects.

### Design

Augment `milestone.description` with a structured preamble block in `_execute_milestone` before
constructing `AgentContext`. No changes to `AgentContext`, `BaseAgent`, or any other agent.

The preamble format:

```
[GOAL CONTEXT]
Goal: {goal.title}
Objective: {goal.objective}
Success condition: {goal.success_condition}
Time horizon: {goal.time_horizon}

Progress so far (step {sequence} of {total}):
{prior_outputs_block}

Learnings from this goal:
{goal.learnings or "(none yet)"}

[YOUR TASK]
{milestone.description}
```

`prior_outputs_block` is built from the list of completed milestones:
- The 3 most recent completed milestones: included in full (output capped at 500 chars each).
- All older completed milestones: title only + first 100 chars of output.
- If no milestones are completed yet: "(no prior steps)".

### Implementation

`_advance_unlocked` already fetches `milestones` before calling `_execute_milestone`. Pass the goal
object and full milestone list into `_execute_milestone`:

```python
# executor.py

async def _execute_milestone(
    self,
    milestone: Milestone,
    goal: Goal,
    all_milestones: list[Milestone],
) -> str:
    prompt = _build_milestone_prompt(milestone, goal, all_milestones)
    ctx = AgentContext(
        session_id=f"goal:{milestone.goal_id}",
        prompt=prompt,
        intent=milestone.intent,
        gate_decision=GateDecision.EXECUTE,
    )
    ...
```

`_build_milestone_prompt` is a pure function (no I/O) that constructs the preamble + task block.
It is unit-testable independently of the executor.

---

## Feature 1b: Procedure Reuse During Active Goals

### Problem

Procedure extraction is currently completion-only. Ze can learn a reusable method after a goal
finishes, but it cannot reliably reuse that method inside the same goal while the method is still
fresh.

### Design

Procedure extraction must be available during an active goal whenever a milestone cluster or gate
redirection reveals a stable method. Any extracted procedure is a goal-local, provisional artifact
until it is promoted to memory on completion.

Required behaviour:

1. Procedure extraction may run after milestone completion, gate redirection, or steer-triggered
   replanning when enough evidence exists to generalise.
2. Any extracted procedure is available to subsequent milestones in the same goal before being
   written to global memory.
3. `GoalPlanner.plan()` and `GoalPlanner.replan_remaining()` must consume both global procedures
   from `MemoryStore` and goal-local provisional procedures when present.
4. On goal completion, stable procedures are promoted to `MemoryStore.propose_procedure()` so
   future goals can reuse them too.

### Implementation

The active-goal procedure source may live in goal state, goal store, or another goal-scoped cache;
the storage choice is an implementation detail. The spec requirement is that the effective prompt
seen by later milestones and replans includes both sets:

```python
procedures = global_memory_procedures + active_goal_procedures
```

If the same procedure exists in both places, the active-goal version wins because it is newer and
more context-specific. Goal-local procedures remain advisory and may be replaced or dropped if
later evidence shows they were too specific.

---

## Feature 2: Execution Trace Store

### Problem

Tool calls made during milestone execution are returned in `AgentResult.tool_calls` but immediately
discarded. There is no way to answer "what did Ze actually do during that step?" after the fact.

### Database Schema

New migration `006_goal_execution_traces.py`:

```sql
CREATE TABLE IF NOT EXISTS goal_execution_traces (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    milestone_id UUID        NOT NULL REFERENCES goal_milestones(id) ON DELETE CASCADE,
    goal_id      UUID        NOT NULL,
    seq          INT         NOT NULL,   -- tool call order within the milestone run
    tool_name    TEXT        NOT NULL,
    args         JSONB       NOT NULL DEFAULT '{}',
    result       TEXT        NOT NULL DEFAULT '',
    duration_ms  INT         NOT NULL DEFAULT 0,
    success      BOOLEAN     NOT NULL,
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS goal_execution_traces_milestone_idx
    ON goal_execution_traces(milestone_id, seq);

CREATE INDEX IF NOT EXISTS goal_execution_traces_goal_idx
    ON goal_execution_traces(goal_id, created_at DESC);
```

Tool call `result` is stored truncated at 2000 chars to bound row size. Full milestone output
remains in `goal_milestones.output` as before.

### Data Type

```python
# ze_personal/goals/types.py

@dataclass
class ExecutionTrace:
    milestone_id: UUID
    goal_id: UUID
    seq: int
    tool_name: str
    args: dict
    result: str
    duration_ms: int
    success: bool
    error: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
```

### Store Protocol Methods

```python
# ze_personal/goals/store.py (Protocol additions)

async def save_traces(self, traces: list[ExecutionTrace]) -> None: ...
async def list_traces(self, milestone_id: UUID) -> list[ExecutionTrace]: ...
```

### Write Path

In `_advance_unlocked`, after `_execute_milestone` returns a result, write its tool calls:

```python
result = await self._execute_milestone(next_milestone, goal, milestones)
# persist traces (fire-and-forget; trace loss is acceptable)
asyncio.create_task(
    self._store.save_traces(_to_traces(next_milestone, result.tool_calls))
)
```

`_to_traces` converts `list[ToolCall]` to `list[ExecutionTrace]`, truncating `result` at 2000 chars.
Also persist on failure path — tool calls made before the exception are on the `GoalExecutionError`
or can be threaded through. If tool calls are unavailable at failure time, save an empty trace list
(the failure itself is already recorded in `milestone.output`).

### Query Tool

```python
# ze_personal/agents/goals/tools.py

@tool(access="read")
async def get_milestone_trace(goal_id: str, milestone_sequence: int, store: GoalStore) -> str:
    """Return the execution trace for a specific milestone — what tools Ze called and what they returned."""
    ...
```

The tool resolves `milestone_id` from `(goal_id, milestone_sequence)` via `list_milestones`, then
calls `store.list_traces(milestone_id)`. Returns a formatted plain-text summary:

```
Milestone 3 execution trace (5 tool calls):
1. web_search("Series B SaaS companies 2025") → 1240ms ✓
   Result: Found 12 companies matching criteria...
2. web_search("Figma Series B funding details") → 890ms ✓
   Result: Figma raised $50M Series B in 2018...
...
```

Add `get_milestone_trace` to `GoalAgent.tools` and update `_AGENT_INSTRUCTIONS` to document it.

---

## Feature 3: Adaptive Replanning Trigger

### Problem

When a milestone fails, Ze marks it `SKIPPED` and immediately advances to the next one. Consecutive
failures cascade: a failed research milestone leaves the next milestone with no input data, which
also fails. Ze can mark a goal "complete" having accomplished nothing.

### Design

Track consecutive failures on the `goals` row. After each milestone failure, increment the counter.
After each success, reset it to zero. When the counter reaches 2, trigger automatic replanning
instead of advancing.

### Schema Change

Add two columns to the `goals` table in migration `006_goal_execution_traces.py`:

```sql
ALTER TABLE goals ADD COLUMN IF NOT EXISTS consecutive_failures INT NOT NULL DEFAULT 0;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS replan_count        INT NOT NULL DEFAULT 0;
```

`replan_count` is a lifetime counter — it never resets. It caps the number of adaptive replans
Ze will attempt for a single goal (limit: 1). Without this cap, two consecutive post-replan
failures trigger another replan, which could loop indefinitely.

### Store Method

```python
# ze_personal/goals/store.py

async def increment_consecutive_failures(self, goal_id: UUID) -> int:
    """Increment and return the new count."""
    ...

async def reset_consecutive_failures(self, goal_id: UUID) -> None: ...

async def increment_replan_count(self, goal_id: UUID) -> int:
    """Increment and return the lifetime replan count."""
    ...
```

### Executor Logic

In `_advance_unlocked`, after milestone completion:

```python
# on success
await self._store.reset_consecutive_failures(goal_id)

# on failure (in the GoalExecutionError catch block)
failures = await self._store.increment_consecutive_failures(goal_id)
if failures >= 2:
    replan_count = await self._store.increment_replan_count(goal_id)
    if replan_count > 1:
        # Already replanned once — don't loop. Pause and surface to user.
        await self._store.update_status(goal_id, GoalStatus.PAUSED)
        await self._push(Notification(
            content=(
                "Multiple steps have failed after replanning. "
                "The goal is paused — send new instructions or abandon it."
            ),
            urgency="high",
        ))
        return
    await self._trigger_adaptive_replan(goal, milestones)
    return
# existing: skip + notify + create_task(advance)
```

`_trigger_adaptive_replan`:
1. Push notification: `"Two steps failed in a row — I'm adapting the plan based on what I've learned so far."`
2. Collect completed milestones (excluding the two that failed).
3. Call `self._planner.replan_remaining(goal, completed, feedback="", next_seq=...)`.
4. Replace pending milestones and gates in the store.
5. Push the new plan as a follow-up notification (title list of pending milestones, max 5):
   `"Adapted plan:\n1. [title]\n2. [title]\n..."`
6. Reset `consecutive_failures` to 0. Do NOT reset `replan_count`.
7. Call `asyncio.create_task(self.advance(goal_id))`.

**Replan failure handling:** If `replan_remaining` raises, log the error, push a notification
(`"Couldn't adapt the plan automatically — please review the goal or send new instructions."`),
and set goal status to `PAUSED`. Do not retry.

---

## Feature 4: Enriched Gate Narrative

### Problem

`_fire_gate` builds a context summary from `m.output[:150]` — 150 characters per milestone. A
research milestone might produce 800 words; the gate message shows one sentence. The user cannot
make a meaningful approve/redirect decision on this information.

### Design

At gate fire time, call `GoalPlanner.synthesize_gate_narrative` to produce a 2–4 sentence summary
of what was accomplished and why execution is pausing. Replace the raw truncated output block in the
gate notification with this narrative. The call is wrapped in a 30-second timeout — on timeout or
any error, fall back to the existing bullet-list format; the gate always fires.

### New Planner Method

```python
# ze_personal/goals/planner.py

_GATE_NARRATIVE_SYSTEM = """\
You summarize completed work at a goal checkpoint. Be concise and specific.
Write 2-4 sentences covering: what was accomplished, any notable findings or blockers,
and why this is a natural pause point. Write in plain language as if briefing the goal owner.
Output only the narrative — no headers, no bullet points.\
"""

async def synthesize_gate_narrative(
    self,
    goal: Goal,
    completed: list[Milestone],
    gate_title: str,
) -> str:
    """Produce a plain-language narrative of completed work for a verification gate."""
    ...
```

The prompt includes goal title, success condition, and each completed milestone's title + output
(capped at 300 chars per milestone).

### Gate Notification Format

Before (current):
```
<b>Goal Title</b> — checkpoint

<b>What was done:</b>
• Milestone A: first 150 chars...
• Milestone B: first 150 chars...

<b>What comes next:</b>
• Milestone C
```

After:
```
<b>Goal Title</b> — checkpoint: Gate Title

{narrative paragraph — 2-4 sentences synthesized by LLM}

<b>What comes next:</b>
• Milestone C
• Milestone D
```

The `plan_summary` stored in `goal_gates.plan_summary` remains the bullet list of upcoming
milestones (this is queryable data, not display content).
The `context_summary` stored in `goal_gates.context_summary` stores the raw bullet list as before
(for future querying). The narrative is generated at notification time only, not persisted.

---

## Interface Contract

### `_build_milestone_prompt(milestone, goal, all_milestones) -> str`

Pure function. No I/O. Returns the full prompt string to pass as `AgentContext.prompt`.

| Input | Notes |
|---|---|
| `milestone` | The milestone to execute |
| `goal` | The parent goal (title, objective, success_condition, time_horizon, learnings) |
| `all_milestones` | Full list — used to compute total count and extract prior completed outputs |

### `GoalStore.save_traces(traces) -> None`

Bulk-inserts `ExecutionTrace` rows. No-op on empty list. Does not raise on individual row errors —
logs and continues (trace loss is acceptable; it must not block goal execution).

### `GoalStore.increment_consecutive_failures(goal_id) -> int`

Atomic `UPDATE goals SET consecutive_failures = consecutive_failures + 1 WHERE id = $1 RETURNING consecutive_failures`. Returns the new count.

### `GoalStore.reset_consecutive_failures(goal_id) -> None`

Sets `consecutive_failures = 0`. Called after any successful milestone.

### Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| `synthesize_gate_narrative` LLM call fails or times out (30s) | Fall back to bullet-list format; log warning; gate still fires |
| `save_traces` write fails | Log warning; goal execution continues unaffected |
| Adaptive replan produces zero milestones | Treat as replan failure; push notification; pause goal |
| Adaptive replan called while another advance is running | Impossible — `_advance_locks` serializes per goal; replan happens inside the lock |
| `get_milestone_trace` called for a milestone with no traces | Return `"No execution trace recorded for this milestone."` This can happen for milestones that failed mid-execution if the process crashed before the fire-and-forget trace write completed. |
| `replan_count` already >= 1 when second batch of failures hits | Skip replan; pause goal; push notification explaining the situation |

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_personal.goals.planner.GoalPlanner` | `synthesize_gate_narrative`, existing `replan_remaining` |
| `ze_personal.goals.store.GoalStore` | New `save_traces`, `list_traces`, `increment_consecutive_failures`, `reset_consecutive_failures`, `increment_replan_count` |
| `ze_core.orchestration.tool` | `@tool` decorator for `get_milestone_trace` |
| Migration `006_goal_execution_traces.py` | New trace table + `goals.consecutive_failures` + `goals.replan_count` columns |

---

## Implementation Notes

- Context injection is in `executor.py` only. No other agent is affected. The preamble is just a
  string — if for some reason the agent finds it noisy, it can be adjusted without schema changes.
- **Ceiling is agent capability, not goal context.** Context injection improves coordination —
  the agent knows why it's running and what came before. It does not improve the underlying
  capability of the agent. A research agent that returns shallow results will still return shallow
  results with full goal context injected. Phase 23 raises the floor; raising the ceiling requires
  improving individual agents' tools and prompts, which is a separate concern.
- The `consecutive_failures` counter resets on any success, not just the immediately prior
  milestone. Two failures separated by a success are treated as independent; only two in a row
  trigger replanning.
- Traces are written as `create_task` (fire-and-forget) to avoid blocking the advance loop on a
  DB write. This means a crash between `_execute_milestone` returning and the task running could
  lose traces for that milestone. This is acceptable — traces are observability data, not
  operational data.
- `synthesize_gate_narrative` uses the same model as `GoalPlanner` (`defaults.MODEL_GOAL_PLAN`).
  It is a short, cheap call — one completion, no tool use.
- The `get_milestone_trace` tool resolves milestone by `(goal_id, sequence)` rather than
  `milestone_id` because the user always thinks in terms of step numbers, not UUIDs.

---

## Testing

| Test | Location |
|---|---|
| `_build_milestone_prompt` with 0, 1, 3, 5 completed milestones | `tests/goals/test_executor.py` |
| `_build_milestone_prompt` truncates older outputs correctly | `tests/goals/test_executor.py` |
| `save_traces` + `list_traces` round-trip | `tests/goals/test_postgres_goal_store.py` |
| `increment_consecutive_failures` atomicity and reset | `tests/goals/test_postgres_goal_store.py` |
| Adaptive replan triggered at 2 consecutive failures | `tests/goals/test_executor.py` |
| Adaptive replan not triggered at 1 failure | `tests/goals/test_executor.py` |
| Adaptive replan failure → goal paused | `tests/goals/test_executor.py` |
| Second batch of failures after replan → goal paused, no second replan | `tests/goals/test_executor.py` |
| Adaptive replan notification includes new plan summary | `tests/goals/test_executor.py` |
| `synthesize_gate_narrative` failure → gate still fires with bullet list | `tests/goals/test_executor.py` |
| `synthesize_gate_narrative` timeout (30s) → gate still fires with bullet list | `tests/goals/test_executor.py` |
| `get_milestone_trace` tool returns formatted output | `tests/agents/goals/test_goal_agent.py` |

All tests mock `GoalStore`, `GoalPlanner`, and `OpenRouterClient`. No real DB or LLM calls.

---

## Open Questions

- [x] Should traces be written synchronously (blocking advance) or as fire-and-forget? → **Fire-and-forget.** Trace loss on crash is acceptable; blocking goal execution for observability data is not.
- [x] Should the gate narrative be persisted or generated at notification time only? → **Generated at notification time only.** No additional column needed; the raw bullet summary remains in `context_summary` for querying.
- [x] Adaptive replan threshold: 2 or 3 consecutive failures? → **2.** Three failures is likely too much silent degradation before self-correction.
- [x] Should the user be notified before adaptive replan or only after? → **Before.** "Two steps failed, adapting the plan..." is sent before the replan LLM call, so the user knows what's happening even if the replan takes a few seconds.
- [x] Can adaptive replan loop infinitely? → **No, capped.** `replan_count` is a lifetime counter that persists across restarts. Ze will attempt at most one adaptive replan per goal. If failures continue after a replan, the goal is paused and the user is asked to intervene.
- [x] Should the adaptive replan notification show the new plan? → **Yes.** After replanning, a second notification lists the new pending milestones (max 5). The user approved the original plan; silently replacing it without showing the result is a trust violation.
