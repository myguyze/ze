# Internal Module Contracts

Function signatures new or changed code must satisfy. REST contracts are in
[rest-api.md](./rest-api.md).

## `ze_automation.workflow.validation.validate_workflow_steps(steps: list[WorkflowStep]) -> None`

- Raises `WorkflowPlanError` on invalid graphs (duplicate ids, dangling branch/
  default_next/skip_to targets).
- Called by: `PostgresWorkflowStore.update_steps`, REST handler, agent tool,
  `WorkflowPlanner.plan` (via existing `validate_step_targets`, extended).

## `ze_automation.workflow.retry.is_transient_failure(error: str | None, exc: BaseException | None = None) -> bool`

- Pure classification — no I/O.
- Returns `False` for verification failures, empty output, unknown errors.
- Returns `True` for rate limits, timeouts, 5xx-class messages (see research.md §4).

## `ze_automation.workflow.store.WorkflowStore.update_steps(workflow_id: UUID, steps: list[WorkflowStep]) -> None`

- Validates via `validate_workflow_steps` before write.
- Updates `workflows.steps` JSONB and `updated_at`; does NOT touch schedule,
  enabled, or execution history.

## `ze_automation.workflow.scheduler.WorkflowScheduler.cancel_execution(workflow_id: UUID, execution_id: UUID) -> Literal["cancelled", "not_running"]`

- Sets cancellation event if execution is registered and running.
- MUST NOT raise for finished executions — returns `"not_running"`.

## `ze_automation.workflow.scheduler.WorkflowScheduler.is_cancelled(execution_id: UUID) -> bool`

- Read-only check for graph nodes.

## Graph nodes (`ze_personal.graph.workflow`)

### `handle_step_failure(state, config) -> dict`

- Input: last step result has `success=False`.
- Reads `step.on_failure`:
  - `fail` → set `current_step_id="FAIL"` (existing terminal).
  - `continue` → next list-order step id or `"END"`.
  - `skip_to:<id>` → target step id.
- MUST record failed step in `workflow_step_results` (already appended by verify).
- MUST check `is_cancelled` before routing — if cancelled, set target to
  `"CANCELLED"` (new terminal).

### `workflow_cancelled(state, config) -> dict`

- Calls `store.finish_execution(execution_id, "cancelled", summary=partial)`.
- Returns user-facing cancellation message.

### `after_verify_step(state) -> str`

- Changed routing keys:
  - Success → `"route_branch"`
  - Failure + retries remaining + transient → `"retry_step"`
  - Failure → `"handle_step_failure"` (was `"workflow_failed"`)

### `workflow_failed(state, config) -> dict`

- When ≥1 successful step exists: LLM-synthesize partial summary into
  `finish_execution(..., status="failed", error=..., summary=synthesized)`.
- When zero successful steps: existing behavior (error only).

### `workflow_synthesize(state, config) -> dict`

- Before marking completed: if zero successful steps → delegate to failed path
  (FR-009b).
- When ≥1 success but some failures recorded → still `completed`; summary notes
  partial step failures if any.

## Graph state extensions (`WorkflowAgentState`)

| Field | Type | Purpose |
|---|---|---|
| `step_attempt` | `int` | Current attempt number for active step (1..3). |

Reset to `1` in `load_workflow_step` when entering a new step (not on retry of
same step — increment before retry edge).

## `ze_automation.agents.workflow.tools.edit_workflow_steps(...) -> dict`

- Resolves workflow by name; accepts step list (JSON or structured args).
- Validates + `store.update_steps`.
- Returns updated step count or `{"error": "…"}`.

## `ze_automation.agents.workflow.tools.cancel_workflow_run(...) -> dict`

- Resolves workflow + latest running execution (or by execution_id if provided).
- Delegates to `scheduler.cancel_execution`.

## `bootstrap._workflow_failure_handler`

- After graph returns with failed status: fetch execution; notification body =
  `execution.summary or str(exc)`, truncated to notifier limit.

## `ze_automation.workflow.planner.WorkflowPlanner.plan`

- `_PLAN_SYSTEM` extended with `on_failure` field guidance and monitoring verify
  criteria template.
- `_parse_step` reads optional `on_failure`, default `"fail"`.
