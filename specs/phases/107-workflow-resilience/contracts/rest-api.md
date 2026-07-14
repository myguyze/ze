# REST API Contracts: Workflow Resilience and Control

All routes under `/api/v0/workflows`, `HTTPBearer` auth via `require_api_key`.
OpenAPI models in `apps/ze-api/ze_api/api/schemas.py`; routes in
`apps/ze-api/ze_api/api/routes/workflows.py`. Regenerate `@ze/client` after
implementation (`make codegen` or project equivalent).

## Existing routes (response shape extended)

### `GET /api/v0/workflows/{workflow_id}` — `getWorkflow`

**Response** `WorkflowDetailResponse` — each step gains:

| Field | Type | Description |
|---|---|---|
| `on_failure` | `string` | `"fail"`, `"continue"`, or `"skip_to:<step_id>"`. Default `"fail"`. |

### `GET /api/v0/workflows/{workflow_id}/executions` — `listWorkflowExecutions`

### `GET /api/v0/workflows/{workflow_id}/executions/{execution_id}` — `getWorkflowExecution`

**Response** `WorkflowExecutionResponse`:

| Field | Change |
|---|---|
| `status` | Now includes `"cancelled"`. |
| `step_results[].attempt_count` | `integer`, default `1`. |
| `step_results[].no_results` | `boolean`, default `false`. |
| `steps_snapshot` | *(107b)* `WorkflowStepResponse[]` — definition frozen at run start; `[]` for legacy executions. |

## New routes

### `PATCH /api/v0/workflows/{workflow_id}/steps` — `updateWorkflowSteps`

Replace the full step list on an existing workflow. Schedule and run history
unchanged.

**Request body** `UpdateWorkflowStepsRequest`:

```json
{
  "steps": [
    {
      "id": "s0",
      "task": "Check for new developments on topic X",
      "agent_hint": "research",
      "intent": "read",
      "verify": "Confirms check ran; empty result is valid if nothing new found",
      "on_failure": "continue",
      "branches": [],
      "default_next": null
    }
  ]
}
```

**Response** `WorkflowDetailResponse` — updated workflow.

**Errors**:
- `404` — workflow not found.
- `422` — validation failure (unknown `skip_to` target, duplicate step id,
  dangling branch/default_next reference). Body includes human-readable reason.

### `POST /api/v0/workflows/{workflow_id}/executions/{execution_id}/cancel` — `cancelWorkflowExecution`

Request cancellation of an in-progress run. Best-effort at step boundary.

**Request body**: none.

**Response** `CancelWorkflowExecutionResponse`:

```json
{
  "status": "cancelled",
  "execution_id": "…",
  "message": "Cancellation requested; run will stop after the current step."
}
```

When execution is not running:

```json
{
  "status": "not_running",
  "execution_id": "…",
  "message": "Execution is not in progress."
}
```

**HTTP status**: `200` for both outcomes (idempotent no-op per FR-022).

## OpenAPI requirements (constitution phase 73)

Each new route MUST declare `response_model`, `summary`, `description`, and
explicit `operation_id` matching the names above.

## WebSocket / chat

No new WebSocket frame types. Agent tools mirror REST capabilities:

| Tool | Equivalent |
|---|---|
| `edit_workflow_steps` | `PATCH …/steps` |
| `cancel_workflow_run` | `POST …/cancel` |

## Failure notification payload (existing path)

`ProactiveNotifier.notify("workflow_failure", …)` body extended:

- When `execution.summary` is set (partial synthesis): use summary text (truncated).
- Otherwise: existing `str(exc)[:200]` behavior.

No new `event_type` — still `workflow_failure:{workflow.id}` with cooldown.
