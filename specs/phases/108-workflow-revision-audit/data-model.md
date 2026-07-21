# Phase 1 Data Model: Workflow Revision Audit

## Entity: WorkflowRevision

Immutable record of one workflow definition change. Written once, never updated or
deleted directly (deletion only cascades from the parent `workflows` row).

**Table**: `workflow_revisions` (migration `zc026`, owned by `ze-automation`)

| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK, server-generated |
| `workflow_id` | `UUID` | FK → `workflows.id`, `ON DELETE CASCADE` (FR-014) |
| `revision_number` | `int` | Monotonically increasing per `workflow_id`, starts at 1 (FR-004). Unique with `workflow_id`. |
| `change_type` | `"created" \| "edited"` | FR-004 |
| `steps_before` | `list[WorkflowStep]` (JSONB) | Empty list when `change_type == "created"` |
| `steps_after` | `list[WorkflowStep]` (JSONB) | Full step list after the change |
| `summary` | `str` | Human-readable diff, generated at write time (FR-007) |
| `actor` | `ActorContext` (flattened into 3 columns, see below) | FR-005, FR-006 |
| `created_at` | `datetime` (UTC) | Server-generated |

**Python dataclass** (`core/ze-automation/ze_automation/workflow/types.py`):

```python
from enum import Enum

class ActorSource(str, Enum):
    AGENT = "agent"
    API = "api"
    SYSTEM = "system"

@dataclass
class ActorContext:
    source: ActorSource
    session_id: str | None = None       # required when source == AGENT
    user_message_id: str | None = None  # required when source == AGENT

@dataclass
class WorkflowRevision:
    id: UUID
    workflow_id: UUID
    revision_number: int
    change_type: str  # "created" | "edited"
    steps_before: list[WorkflowStep]
    steps_after: list[WorkflowStep]
    summary: str
    actor: ActorContext
    created_at: datetime
```

**Validation rules**:
- `revision_number >= 1`, unique per `(workflow_id, revision_number)` — enforced by DB
  unique index; application computes `next = COALESCE(MAX(revision_number), 0) + 1`
  inside the same transaction as the write it's auditing.
- `steps_before == []` iff `change_type == "created"`.
- `actor.source == ActorSource.AGENT` implies `session_id is not None and
  user_message_id is not None` at the point the tool constructs `ActorContext`; if
  either is missing (non-chat code path calling the tool, e.g. a future scheduled
  agent invocation), `source` falls back to `ActorSource.SYSTEM` per spec Edge Case
  ("best-effort actor source; conversation link is omitted").
- No revision row is written when: validation of the incoming steps fails (existing
  `validate_workflow_steps` raises `WorkflowPlanError`), or the incoming `steps_after`
  is structurally identical (via `_step_to_dict` comparison) to the current stored
  steps (FR-008).

**State transitions**: None — rows are write-once. The *workflow* they describe
transitions through revisions, but each `WorkflowRevision` row itself has no lifecycle
beyond insert.

## Entity: Change Summary (derived, not stored separately)

Computed once at write time by `revision_summary.build_change_summary(before, after)`
and persisted into `WorkflowRevision.summary`. Not a separate table — see
research.md §3 for the diff algorithm (per-step-id add/remove/field-change detection
over `task, agent_hint, verify, intent, branches, default_next, on_failure`).

## Relationships

```
workflows (1) ──────────< (N) workflow_revisions      [ON DELETE CASCADE]
sessions  (1) ┄┄┄ soft ┄┄┄< (N) workflow_revisions.actor_session_id    [no FK, cross-chain]
messages  (1) ┄┄┄ soft ┄┄┄< (N) workflow_revisions.actor_user_message_id [no FK, cross-chain]
```

`workflow_executions` (107b) is a sibling, not a parent/child of `workflow_revisions`:
both key off `workflow_id` and `created_at`, and Story 4 correlates them by comparing
`workflow_executions.started_at` against `workflow_revisions.created_at` — no direct
FK between the two tables.

## Store interface additions

`core/ze-automation/ze_automation/workflow/store.py` (`WorkflowStore` Protocol):

```python
async def create(self, workflow: Workflow, actor: ActorContext | None = None) -> UUID:
    """Existing method — gains optional actor param; defaults to ActorSource.SYSTEM."""

async def update_steps(
    self, workflow_id: UUID, steps: list[WorkflowStep], actor: ActorContext | None = None
) -> None:
    """Existing method — gains optional actor param; defaults to ActorSource.SYSTEM."""

async def list_revisions(
    self, workflow_id: UUID, limit: int = 20, offset: int = 0
) -> list[WorkflowRevision]:
    """New. Ordered revision_number DESC (== created_at DESC)."""
```

`actor: ActorContext | None = None` defaults so every existing call site
(`create_workflow`/`edit_workflow_steps` tools before this phase's tool-signature
changes land, any test fixture, scheduler internals) keeps compiling; the default
maps to `ActorContext(source=ActorSource.SYSTEM)` inside the store implementation.
