# Phase 0 Research: Workflow Resilience and Control

All items resolved by reading the existing workflow implementation (`core/ze-automation`,
`plugins/ze-personal/ze_personal/graph/workflow.py`, `bootstrap.py`). No external
library research required. No NEEDS CLARIFICATION markers remain.

## 1. Where does step failure currently abort the run?

**Decision**: `after_verify_step` (`workflow.py:367-371`) routes to `workflow_failed`
whenever the last `StepResult.success` is `False`. There is no per-step policy —
all failures are terminal. `_fail_step` persists the failed result immediately.

**Rationale**: Confirmed by reading graph edges and `plugins/ze-personal/tests/graph/test_workflow.py`.

**Alternatives considered**: Handling `on_failure` inside `_fail_step` before persisting —
rejected because routing (continue vs skip_to vs fail) belongs in a dedicated
`handle_step_failure` node so `after_verify_step` stays a simple predicate and
retry logic can intercept before failure is finalized.

## 2. How are steps snapshotted for in-progress runs?

**Decision**: `bootstrap._workflow_executor` copies `workflow.steps` into
`initial_state["workflow_steps"]` at invoke time (`bootstrap.py:236`). Edits to
the workflow row after trigger do not mutate in-flight graph state — FR-019 is
already satisfied without new persistence.

**Rationale**: Executor re-fetches workflow once per trigger/schedule fire; graph
state is the snapshot.

**Alternatives considered**: Persisting step snapshot on `workflow_executions` row —
rejected as unnecessary given graph state already freezes definitions.

## 3. How does failure notification work today?

**Decision**: `WorkflowScheduler._run_execution` checks persisted execution status
after graph returns; if `failed`, calls `_workflow_failure_handler` which sends
`ProactiveNotifier.notify("workflow_failure", title, str(exc)[:200], ...)`
(`bootstrap.py:250-268`). `workflow_failed` node sets `execution.error` via
`store.finish_execution(execution_id, "failed", error=error_msg)` but does not
populate `summary` with partial output.

**Rationale**: Partial synthesis (FR-010) extends `workflow_failed` to LLM-summarize
successful steps into `summary`, and `_workflow_failure_handler` prefers
`execution.summary` (truncated) over bare `str(exc)` for the notification body.

**Alternatives considered**: Separate notification type for partial failures — rejected
per spec clarification (same path).

## 4. Retry placement and backoff

**Decision**: Add `step_attempt: int` to `WorkflowAgentState` (reset to 1 in
`load_workflow_step` only on fresh step load, incremented on retry). On transient
failure detected in `verify_step` / tool-failure path **before** `_fail_step`
finalizes: if `step_attempt < STEP_MAX_ATTEMPTS` (3) and `is_transient_failure(error)`,
return state patch that routes back to `load_workflow_step` via new edge
`retry_step` without recording a final failed result. Fixed **2 second**
`asyncio.sleep` between attempts (planning default — not user-configurable).

**Transient classification** (`retry.py`): `RateLimitError`, `AgentTimeoutError`,
OpenRouter 5xx messages, tool errors containing "timeout", "rate limit", "503",
"502", "429". Non-transient: verification failure, empty output, tool logic errors.

**Rationale**: OpenRouter client already retries in-flight HTTP (`ze_core/openrouter/client.py`);
workflow-level retries cover verify failures caused by flaky tool/LLM responses and
agent execution errors that exhaust client retries. Fixed delay avoids immediate
re-hit on rate limits.

**Alternatives considered**: Exponential backoff — deferred; fixed 2s sufficient for
single-user scheduled workflows. Per-step configurable limits — out of scope per spec.

## 5. `on_failure` routing mechanics

**Decision** (from spec clarification):
- `fail` (default): existing behavior → `workflow_failed`.
- `continue`: set `current_step_id` to `_next_step_id_in_list(steps, step_id)` or `END`; record failed step in history; proceed.
- `skip_to:<step_id>`: set `current_step_id` to target; validate target exists at plan/save time via extended `validate_step_targets`.

New graph node `handle_step_failure` runs when `after_verify_step` detects failure.
Edge `after_handle_step_failure` routes to `load_workflow_step`, `workflow_failed`,
or `workflow_synthesize` (if next is END after continue on last step).

**Overall run status** (FR-009a/b): `workflow_synthesize` checks if any
`StepResult.success`; if none → `finish_execution("failed", summary=all-failures)`;
if ≥1 → `finish_execution("completed", summary=...)` even when some steps failed
with `on_failure: continue`.

**Alternatives considered**: Separate `critical: bool` — rejected in clarification.

## 6. "No results" vs malfunction in verify

**Decision**: Extend verify LLM JSON schema to
`{"pass": bool, "no_results": bool, "reason": str}`. When `pass=true` and
`no_results=true`, record `StepResult(success=True, no_results=True, output=reason)`.
Planner `_PLAN_SYSTEM` gains guidance: monitoring/check steps MUST author verify
criteria accepting empty findings; may set `on_failure: continue` when appropriate.

**Rationale**: Root cause of production false failure was verify treating empty
findings as fail; FR-012/FR-013 addressed at verify + planner layers.

**Alternatives considered**: Hard-coded task-keyword heuristics — rejected; planner
authoring is the durable fix.

## 7. Cancellation architecture

**Decision**: `WorkflowScheduler` holds `CancellationRegistry: dict[UUID, asyncio.Event]`.
Registered in `trigger_now` / `_run_workflow`; cleared in `_run_execution` finally block.
`cancel_execution(workflow_id, execution_id)` sets event; returns False if not running.
Graph nodes `load_workflow_step` and `handle_step_failure` call
`scheduler.is_cancelled(execution_id)` — if set, route to new `workflow_cancelled`
node → `finish_execution("cancelled", summary=partial)`.

**Rationale**: Best-effort at step boundaries (spec Assumption); no agent abort
mid-tool-call in this phase. In-memory registry sufficient for single-process
single-user deployment; execution_id is the key.

**Alternatives considered**: DB flag polled each step — adds write latency;
in-memory event + persist cancelled status at end is sufficient.

## 8. Step editing surface

**Decision** (from spec clarification): `PATCH /api/v0/workflows/{id}/steps` +
`edit_workflow_steps` agent tool calling shared `validate_workflow_steps()` +
`store.update_steps()`. ze-web: cancel button only on `WorkflowDetailPage`.

**Alternatives considered**: Full graph editor UI — out of scope.
