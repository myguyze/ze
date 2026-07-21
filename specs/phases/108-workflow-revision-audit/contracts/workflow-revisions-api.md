# Contract: Workflow Revisions REST API

New route added to `apps/ze-api/ze_api/api/routes/workflows.py`, same router
(`tags=["workflows"]`, `dependencies=[Depends(require_api_key)]`) as existing workflow
routes. `operation_id`s follow the existing `listWorkflowExecutions` naming style so
`@myguyze/ze-client` codegen produces matching named functions.

## `GET /api/v0/workflows/{workflow_id}/revisions`

**operation_id**: `listWorkflowRevisions`

**Summary**: List workflow revisions

**Description**: Return the revision history for a workflow, newest first.

**Path params**:
- `workflow_id: UUID`

**Query params**:
- `limit: int = 20` (`ge=1, le=100`)
- `offset: int = 0` (`ge=0`)

**Response**: `200 OK`, `list[WorkflowRevisionResponse]`

```jsonc
[
  {
    "id": "b3f...uuid",
    "workflow_id": "a1c...uuid",
    "revision_number": 3,
    "change_type": "edited",           // "created" | "edited"
    "steps_before": [ /* WorkflowStepResponse[] */ ],
    "steps_after": [ /* WorkflowStepResponse[] */ ],
    "summary": "Step s3: on_failure fail → continue",
    "actor_source": "agent",            // "agent" | "api" | "system"
    "actor_session_id": "thread-abc123",   // null unless actor_source == "agent"
    "actor_user_message_id": "c9e...uuid", // null unless actor_source == "agent"
    "created_at": "2026-07-20T14:03:11Z"
  }
]
```

**Errors**:
- `404 Not Found` — `workflow_id` does not exist (mirrors `getWorkflow`'s 404 shape).

**Pydantic schemas** (`apps/ze-api/ze_api/api/schemas.py`):

```python
class ActorContextResponse(BaseModel):
    source: Literal["agent", "api", "system"]
    session_id: str | None = None
    user_message_id: str | None = None

class WorkflowRevisionResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    revision_number: int
    change_type: Literal["created", "edited"]
    steps_before: list[WorkflowStepResponse]
    steps_after: list[WorkflowStepResponse]
    summary: str
    actor_source: Literal["agent", "api", "system"]
    actor_session_id: str | None = None
    actor_user_message_id: str | None = None
    created_at: datetime
```

(Flattened `actor_*` fields on the response, matching the flattened DB columns —
simpler for the generated TS client than a nested object; internal dataclass keeps
`ActorContext` nested for readability.)

## No other new endpoints in v1

- Rollback/restore (`POST .../revisions/{id}/restore`) — out of scope (spec "Out of
  Scope (Deferred)").
- Single-revision fetch (`GET .../revisions/{revision_id}`) — not required by any user
  story; the list response carries full before/after already, so detail expansion in
  the UI (Story 2, Acceptance Scenario 3) is served from the same list payload.
- Story 4's "revisions after this run" is served by client-side filtering of the same
  list response (see research.md §8) — no `?since=` param in v1.

## Existing endpoints — behavior changes (no signature changes)

- `PATCH /{workflow_id}/steps` (`updateWorkflowSteps`): unchanged request/response
  contract. Internally now writes a revision row via `store.update_steps(...,
  actor=ActorContext(source=ActorSource.API))` — invisible to the API consumer except
  that a new row is now retrievable via the new list endpoint.
- Workflow creation (currently only reachable via the `create_workflow` agent tool —
  there is no REST create endpoint today): the tool passes
  `actor=ActorContext(source=ActorSource.AGENT, session_id=..., user_message_id=...)`.

## Agent tool contract changes

`edit_workflow_steps` and `create_workflow`
(`core/ze-automation/ze_automation/agents/workflow/tools.py`) gain two
internally-injected parameters. These are **not** part of the LLM-visible tool schema
(no change to the `@tool(description=...)` text or to what the LLM must supply) — they
arrive via `_merge_deps` from the agent's `deps` dict, same mechanism as `store`:

```python
async def edit_workflow_steps(
    store: WorkflowStore,
    workflow_name: str,
    steps_json: str,
    session_id: str | None = None,        # NEW — injected, not LLM-supplied
    user_message_id: str | None = None,    # NEW — injected, not LLM-supplied
) -> dict: ...

async def create_workflow(
    store: WorkflowStore,
    planner: WorkflowPlanner,
    scheduler: WorkflowScheduler,
    workflow_name: str,
    description: str,
    schedule_description: str = "",
    session_id: str | None = None,        # NEW — injected, not LLM-supplied
    user_message_id: str | None = None,    # NEW — injected, not LLM-supplied
) -> dict: ...
```
