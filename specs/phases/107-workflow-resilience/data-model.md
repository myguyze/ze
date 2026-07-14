# Phase 1 Data Model: Workflow Resilience and Control

JSONB field extensions on `workflows.steps` and `workflow_executions.step_results`
require no migration. **107b follow-up** adds `workflow_executions.steps_snapshot`
(JSONB) and extends the `status` CHECK constraint to include `cancelled`
(migration `zc025` in ze-automation chain; `zc022` is owned by ze-core).

## Extended entities

### `WorkflowStep` (`ze_automation/workflow/types.py`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `on_failure` | `str` | `"fail"` | One of: `"fail"`, `"continue"`, `"skip_to:<step_id>"` |

Existing fields unchanged: `task`, `agent_hint`, `verify`, `intent`, `id`,
`branches`, `default_next`.

**Validation rules** (shared `validation.py`):
- `on_failure` MUST be `"fail"`, `"continue"`, or match `^skip_to:[a-zA-Z0-9_-]+$`.
- `skip_to` target MUST exist in the step list (same rule as `branches[].to` / `default_next`).
- Step `id` values MUST be unique within the workflow.

**JSONB serialization** (`postgres._step_to_dict` / `_step_from_dict`):
- Persist `on_failure`; omit key when `"fail"` for backward compatibility with
  existing workflows (deserializer defaults to `"fail"`).

### `StepResult` (`ze_automation/workflow/types.py`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `attempt_count` | `int` | `1` | Total execution attempts for this step (1 = first try). |
| `no_results` | `bool` | `False` | True when step succeeded but found nothing new (monitoring shape). |

Existing fields unchanged: `step_index`, `task`, `output`, `success`, `error`,
`duration_ms`, `step_id`, `branch_taken`.

**Validation rules**:
- `attempt_count >= 1`.
- `no_results=True` implies `success=True`.
- Failed results MUST have `no_results=False`.

### `WorkflowExecution` (`ze_automation/workflow/types.py`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `steps_snapshot` | `list[WorkflowStep]` | `[]` | Immutable copy of `workflows.steps` frozen at `start_execution` (107b). NULL/empty for legacy rows. |

**Status enum** (TEXT column; CHECK constraint updated in 107b migration):

| Status | When |
|---|---|
| `running` | Execution in progress (existing). |
| `completed` | Run finished; ≥1 successful step (FR-009a), including mixed outcomes. |
| `failed` | Step with `on_failure: fail` failed, unrecoverable error, all steps failed with continue, or stale recovery (existing + FR-009b). |
| `cancelled` | User requested cancellation; no further steps after current boundary (FR-021). |

**Validation rules**:
- `steps_snapshot` MUST NOT be updated after insert (immutable).
- Populated at the same time as graph initial state (same step list as `workflow.steps` at trigger).

## Migration (107b only)

### `zc025_workflow_execution_snapshot_and_cancelled.py`

```sql
-- Extend status CHECK to include cancelled (drop/recreate or replace constraint)
ALTER TABLE workflow_executions
  ADD COLUMN IF NOT EXISTS steps_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb;
```

- Existing rows keep `steps_snapshot = []`; UI treats empty snapshot as legacy (FR-018g).
- New executions MUST write full step list at start (non-empty when workflow has steps).

## New value objects (in-memory)

### `CancellationRegistry` (`ze_automation/workflow/scheduler.py`)

```python
class CancellationRegistry:
    def register(self, execution_id: UUID) -> asyncio.Event: ...
    def cancel(self, execution_id: UUID) -> bool: ...
    def is_cancelled(self, execution_id: UUID) -> bool: ...
    def unregister(self, execution_id: UUID) -> None: ...
```

Process-local; cleared on execution completion.

### `TransientFailureClassifier` (`ze_automation/workflow/retry.py`)

```python
STEP_MAX_ATTEMPTS: int = 3          # 1 initial + 2 retries
RETRY_DELAY_SECONDS: float = 2.0

def is_transient_failure(error: str | None, exc: BaseException | None = None) -> bool: ...
```

## REST schema mirrors (Pydantic — `ze_api/api/schemas.py` only)

### `WorkflowStepResponse` additions

- `on_failure: str = "fail"`

### `StepResultResponse` additions

- `attempt_count: int = 1`
- `no_results: bool = False`

### `WorkflowExecutionResponse` additions (107b)

- `steps_snapshot: list[WorkflowStepResponse]` — empty for legacy executions; populated for runs started after 107b.

### `UpdateWorkflowStepsRequest` (new)

```python
class UpdateWorkflowStepsRequest(BaseModel):
    steps: list[WorkflowStepInput]

class WorkflowStepInput(BaseModel):
    task: str
    agent_hint: str | None = None
    verify: str | None = None
    intent: str = "execute"
    id: str
    branches: list[BranchInput] = []
    default_next: str | None = None
    on_failure: str = "fail"
```

### `CancelWorkflowExecutionResponse` (new)

```python
class CancelWorkflowExecutionResponse(BaseModel):
    status: Literal["cancelled", "not_running"]
    execution_id: UUID
    message: str
```

## State transitions (execution)

```text
running ──(all steps succeed)──► completed
running ──(on_failure:fail step fails)──► failed
running ──(all steps fail, all continue)──► failed
running ──(mixed: ≥1 success, reach END)──► completed
running ──(cancel requested at boundary)──► cancelled
running ──(uncaught exception)──► failed
running ──(stale timeout recovery)──► failed   [existing]
```

## Relationships

Unchanged: `Workflow 1─* WorkflowExecution`, steps embedded in workflow JSONB,
step results embedded in execution JSONB.
