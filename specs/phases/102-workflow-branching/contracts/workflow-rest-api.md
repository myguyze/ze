# Contracts: Workflow REST API

Existing, shipped endpoints in `apps/ze-api/ze_api/api/routes/workflows.py`
(all under `require_api_key`, tagged `workflows`). No endpoint is added, removed,
renamed, or has a path/method change. Response *shapes* gain optional fields.

## `GET /api/v0/workflows` — `listWorkflows`

Unchanged. Returns `list[WorkflowResponse]` — this model never included steps,
so it's unaffected by branching.

## `GET /api/v0/workflows/{workflow_id}` — `getWorkflow`

Unchanged status codes (200, 404). `WorkflowDetailResponse.steps` — each
`WorkflowStepResponse` gains:

```json
{
  "task": "...",
  "agent_hint": "research",
  "verify": "...",
  "id": "s1",
  "branches": [{"condition": "invoice found", "to": "s3"}],
  "default_next": null
}
```

A pre-existing workflow (created before this feature) returns `"branches": []`,
`"default_next": null`, and an auto-backfilled `"id"` (`"s0"`, `"s1"`, ... in
list order) — indistinguishable in shape from a newly authored linear workflow.

## `GET /api/v0/workflows/{workflow_id}/executions` — `listWorkflowExecutions`

Unchanged status codes. Each `WorkflowExecutionResponse.step_results` entry
(`StepResultResponse`) gains:

```json
{
  "step_index": 2,
  "task": "...",
  "output": "...",
  "success": true,
  "error": null,
  "duration_ms": 0,
  "step_id": "s2",
  "branch_taken": "invoice found"
}
```

`step_index` now means "the Nth step executed in this run" (0-based, execution
order) rather than "position in `Workflow.steps`" — see `data-model.md`. For any
workflow with no branches (including all pre-existing ones), execution order and
array order are identical, so this is not observable as a behavior change for the
non-branching case; it only becomes observable (and necessary) once a run
actually branches or loops.

## `POST /api/v0/workflows/{workflow_id}/trigger` — `triggerWorkflow`

Unchanged. Returns `TriggerWorkflowResponse` — no step-shaped data.

## Client codegen

After schema changes land, run `make codegen` to regenerate
`@myguyze/ze-client` (OpenAPI → TypeScript via `@hey-api/openapi-ts`, per
Phase 72). `apps/ze-web` consumes the regenerated types with no manual edits to
`entities/workflow/api/*` — those hooks are thin `useQuery`/`useMutation`
wrappers with no field-level knowledge baked in.
