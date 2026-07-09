# Phase 1 Data Model: Workflow Conditional Branching

All types below live in `core/ze-automation/ze_automation/workflow/types.py`
unless noted. Every new field is optional with a default that reproduces today's
behavior exactly — this is an additive change to existing dataclasses, not a
new schema.

## `Branch` (new)

| Field | Type | Notes |
|---|---|---|
| `condition` | `str` | Natural-language predicate describing the step outcome this branch matches (e.g. "an invoice was found"). Evaluated by LLM classification, same style as `WorkflowStep.verify`. |
| `to` | `str` | Target: another step's `id` in the same workflow, or the literal `"END"` (finish the workflow successfully) or `"FAIL"` (fail the workflow run). |

Belongs to exactly one `WorkflowStep`. A step's `branches` list is evaluated in
order; first match wins (spec Edge Cases).

## `WorkflowStep` (extended)

| Field | Type | Change |
|---|---|---|
| `id` | `str` | **New.** Stable, unique within the owning `Workflow.steps`. Assigned by the planner when branches are used; backfilled as `f"s{index}"` for any step lacking one when read from storage (Decision 3, research.md). |
| `task` | `str` | unchanged |
| `agent_hint` | `str \| None` | unchanged |
| `verify` | `str \| None` | unchanged |
| `intent` | `str` | unchanged |
| `branches` | `list[Branch]` | **New.** Default `[]`. Empty list ⇒ step behaves exactly as today (FR-005). |
| `default_next` | `str \| None` | **New.** Default `None`. Target used when `branches` is non-empty but none match, or to explicitly override plain sequential order even with no branches (FR-006). Same target vocabulary as `Branch.to`. |

**Validation rule** (enforced at workflow create/edit time, not at the dataclass
level — see `contracts/workflow-tools.md`): every `Branch.to` and every
`default_next` in a `Workflow.steps` list must equal `"END"`, `"FAIL"`, or the
`id` of another step in the same list. `id` values must be unique within the
list.

## `StepResult` (extended)

| Field | Type | Change |
|---|---|---|
| `step_index` | `int` | unchanged — now represents *execution order within the run* (the Nth step executed), not a position in `Workflow.steps`, since branching/looping means steps no longer execute in list order. |
| `step_id` | `str` | **New.** The `WorkflowStep.id` that was executed, so a run's path can be reconstructed as the ordered sequence of `step_id`s in `WorkflowExecution.step_results` (FR-013). |
| `task` | `str` | unchanged |
| `output` | `str` | unchanged |
| `success` | `bool` | unchanged |
| `error` | `str \| None` | unchanged |
| `duration_ms` | `int` | unchanged |
| `branch_taken` | `str \| None` | **New.** Default `None`. The `Branch.condition` text that matched at this step (or `None` if the step had no branches, or if none matched and a fallback was used). Answers "why did the run go this way" per FR-013/SC-004 without needing anything beyond the run's own record. |

## `Workflow` — unchanged

Field set is identical (`id`, `name`, `description`, `steps`, `schedule`,
`enabled`, `last_run_at`, `next_run_at`, `created_at`, `updated_at`). Only the
shape of the objects inside `steps` changes.

## `WorkflowExecution` — unchanged

Field set is identical. `step_results` now carries richer per-entry data (above)
but the container type and its meaning ("append-only log of this run's executed
steps in order") are unchanged.

## Transient execution state (not persisted)

Added to `WorkflowAgentState` in `plugins/ze-personal/ze_personal/graph/workflow.py`
(`total=False`, matching the existing extension pattern):

| Field | Type | Purpose |
|---|---|---|
| `current_step_id` | `str` | Replaces `current_step_index` as the source of truth for "which step runs next." Kept alongside `current_step_index` only if needed for any lingering index-based code path; new code is id-keyed throughout. |
| `steps_by_id` | `dict[str, WorkflowStep]` | Built once from `workflow_steps` when a run starts; avoids re-scanning the list on every node. |
| `visit_counts` | `dict[str, int]` | Per-run tally of how many times each step id has been entered; enforces the loop guard (FR-008: fail once a step's count exceeds 1 + 3 = 4). |

## Persistence mapping (JSONB, additive — no migration)

`core/ze-automation/ze_automation/workflow/postgres.py`:

- `_step_to_dict` / `_step_from_dict`: add `id`, `branches` (list of
  `{"condition", "to"}` dicts), `default_next`. `_step_from_dict` backfills
  `id = f"s{index}"` when the key is absent (legacy rows) — requires the caller
  to pass the index, so its signature gains an `index: int` parameter used only
  for the backfill default.
- `_step_result_to_dict` / `_step_result_from_dict`: add `step_id`,
  `branch_taken`, both defaulting to `None`/absent-safe on read for legacy
  execution rows.

No `ALTER TABLE` is needed: `workflows.steps` and `workflow_executions.step_results`
are already `jsonb`/`jsonb[]`-via-array columns that accept arbitrary additional
keys per element.

## REST schema mapping (`apps/ze-api/ze_api/api/schemas.py`)

These Pydantic response models mirror the dataclasses above for the existing
`GET /api/v0/workflows*` endpoints (`ze_api/api/routes/workflows.py`) and the
existing web UI that consumes them via the codegen'd `@myguyze/ze-client` SDK.
All additions are optional/nullable-safe so the codegen'd client's existing
callers don't need type-level changes beyond what the new fields require.

| Model | Change |
|---|---|
| `WorkflowStepResponse` | + `id: str`, `branches: list[BranchResponse]` (new small model: `condition: str`, `to: str`), `default_next: str \| None` |
| `StepResultResponse` | + `step_id: str`, `branch_taken: str \| None` |
| `WorkflowResponse`, `WorkflowDetailResponse`, `WorkflowExecutionResponse`, `TriggerWorkflowResponse` | unchanged — they only wrap the two models above |

`core/ze-automation/ze_automation/rest.py` (`get_workflow`, `list_workflow_executions`)
builds the plain dicts these schemas validate — extended in lockstep with the
dataclass changes above (same fields, same names, so `WorkflowStepResponse.model_validate(s)`
in `routes/workflows.py` needs no route-level changes).

After the Python-side change, `make codegen` regenerates `@myguyze/ze-client` so
`WorkflowStepResponse`/`StepResultResponse`'s TypeScript types pick up the new
fields automatically — no manual type editing in `ze-web`.

## Existing UI rendering fix (not a new UI)

`apps/ze-web/src/widgets/workflow-steps/ui/WorkflowStepsList.tsx` and
`apps/ze-web/src/widgets/workflow-executions/ui/LiveRunPanel.tsx` both currently:

1. Iterate the static `steps` array (`steps.map((step, i) => ...)`), treating
   array index `i` as ground truth for "which step is this."
2. Match a run result via `stepResults.find(r => r.step_index === i)`.
3. Infer "currently running" / "pending" by comparing `stepResults.length`
   (`completedCount`) against the array index.

All three assumptions break once `StepResult.step_index` means "Nth step executed
in this run" (this plan's change) rather than "position in the authored steps
array": a loop revisiting one step multiple times only ever renders one row
(`.find()` short-circuits on the first match), and the running/pending inference
points at the wrong row as soon as execution order diverges from array order.

**Fix**: both components switch their primary iteration source from
`workflow.steps` to `execution.step_results` (already execution-ordered) when an
execution is present, keying each rendered row by `step_id` + its position within
`step_results` (not by array index), and looking up the step's static metadata
(`task`, `agent_hint`, ...) from a `Map<string, WorkflowStepResponse>` built from
`workflow.steps` by `id`. When no execution exists yet (a workflow that has never
run), both components keep rendering `workflow.steps` in authored order exactly
as today — this is the only case where "array order" is still the right thing to
show, since there's no execution path yet to reflect.

### "Not taken this run" state (FR-016)

`StepState` (currently `"completed-ok" | "completed-fail" | "running" |
"failed-inferred" | "pending"` in both widgets) gains a sixth value:
`"not-taken"`. After building the executed-`step_id` set from
`execution.step_results`, any step in `workflow.steps` whose `id` is **not** in
that set, on a **completed or failed** (non-running) execution, resolves to
`"not-taken"` rather than `"pending"` — `"pending"` is reserved for steps that
genuinely haven't happened yet on a still-running execution. Visually: same
dimmed treatment already used for `"pending"`/`"failed-inferred"` text color,
plus a small inline label ("not taken this run") so it reads distinctly from
"hasn't happened yet." For a workflow with no branches, the executed-`step_id`
set is always exactly `workflow.steps`' full id set on any completed run, so
`"not-taken"` never fires — zero visual change for the non-branching case
(SC-006).

### Live progress indicator (FR-017)

`LiveRunPanel`'s header currently renders `Step {completedCount + 1} / {workflow.steps.length}`
(running) or `{completedCount} / {workflow.steps.length} steps` (finished). Both
become conditional on `hasBranches` (Decision 6, research.md):

- `hasBranches === false` (today's case, and every pre-existing workflow):
  unchanged — fixed `N / total`.
- `hasBranches === true`: drop the denominator — `Step {completedCount + 1}…`
  while running, `{completedCount} steps` once finished. No fabricated total is
  ever shown for a workflow whose actual path length isn't fixed.

## State transitions (execution path)

```
load_workflow_step(current_step_id)
   → embed_route → … → execute_tool → write_memory
   → verify_step
       ├─ step failed → workflow_failed (END)
       └─ step succeeded → route_branch   [NEW]
             ├─ branches defined, one matches   → current_step_id = branch.to
             ├─ branches defined, none match    → current_step_id = default_next or next-in-list
             ├─ no branches                     → current_step_id = default_next or next-in-list
             ├─ resolved target == "END"        → workflow_synthesize (END)
             ├─ resolved target == "FAIL"       → workflow_failed (END)
             └─ resolved target's visit_count > 4 → workflow_failed (END), loop-guard error
       → (else) load_workflow_step(current_step_id)  [loop back]
```
