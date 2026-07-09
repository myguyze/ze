# Phase 0 Research: Workflow Conditional Branching

No open `NEEDS CLARIFICATION` markers remain in the spec or Technical Context —
all four clarification-session answers (SC-005 threshold, FR-008 loop-count
semantics, FR-016 skipped-step display, FR-017 progress-indicator denominator)
are already integrated into `spec.md`. The items below are design decisions made
while translating the spec into a plan, not unresolved unknowns.

## Decision 1: How branch conditions get evaluated

**Decision**: A branching step gets one additional LLM call — a small classification
prompt handed the step's resolved output plus the ordered list of `(condition, to)`
pairs, asking which one (if any) matches — using the same model already configured
for the verify gate (`workflow_verify` model key, `MODEL_WORKFLOW_VERIFY` default).
This runs in a new `route_branch` graph node, strictly after `verify_step` has
already confirmed the step succeeded.

**Rationale**: The codebase already has exactly this shape of call in
`verify_step` (`plugins/ze-personal/ze_personal/graph/workflow.py:93-111`) — a
natural-language judge prompt over step output, parsed as JSON. Reusing the same
model/config/error-tolerance pattern (log-and-fall-through on parse failure,
mirroring `workflow_verify_error` handling) keeps this consistent with existing
conventions rather than inventing a second evaluation mechanism.

**Alternatives considered**:
- *Merge branch classification into the existing verify call* (one LLM call
  returns both pass/fail and, if passing, which branch matched). Rejected: FR-009
  requires a failed step to never reach branch evaluation at all; conflating the
  two makes it harder to guarantee that ordering and complicates the verify
  prompt/schema for the common (non-branching) case, which must stay exactly as
  cheap and simple as it is today.
- *Structured/expression-based conditions* (e.g., evaluate a boolean expression
  against structured tool output) instead of LLM classification. Rejected by the
  spec's own Assumptions section — step output is unstructured natural language
  today, same as `verify`, so a structured condition language has no data to
  operate on without a much larger change to how steps report output.

## Decision 2: Where loop/visit tracking lives

**Decision**: `visit_counts: dict[str, int]` (step id → times entered) lives in
`WorkflowAgentState` alongside the existing `workflow_step_results`, not in a new
persisted column. It's naturally scoped to a single run because LangGraph state is
per-invocation (checkpointed per `thread_id`/execution), matching how
`current_step_index` already works today.

**Rationale**: FR-008's guard is explicitly per-run ("within that run"); nothing
in the spec asks for cross-run loop memory. Keeping it in transient graph state
avoids a schema change and mirrors the existing `workflow_step_results` pattern
exactly.

**Alternatives considered**: Persisting visit counts on `WorkflowExecution` in
Postgres. Rejected: unnecessary — `step_results` already accumulates one entry per
step *execution* (not per step id), so revisits are already implicitly counted by
`len([r for r in step_results if r.step_id == target])`; the in-state dict is just
a cheap running tally to avoid recomputing that scan on every node.

## Decision 3: Where step ids get backfilled for legacy workflows

**Decision**: Backfill happens once, at the Postgres → `WorkflowStep` boundary
(`_step_from_dict` in `postgres.py`), assigning `f"s{index}"` to any step object
missing an `id` key, using its position in the stored list.

**Rationale**: `PostgresWorkflowStore.get`/`get_by_name`/`list_all`/
`list_enabled_scheduled` all route through `_row_to_workflow` → `_step_from_dict`
(`postgres.py:69-81`), and `agents/workflow/tools.py` (`list_workflows`,
`get_workflow`, `create_workflow`) all go through the store — so backfilling at
this single boundary means every caller (graph executor, agent tools) sees
consistent, already-populated ids with no special-casing anywhere else.

**Alternatives considered**: Backfilling ids lazily inside the graph executor
only. Rejected: `agents/workflow/tools.py:get_workflow` also needs to report step
ids/branches to be useful, and duplicating the backfill logic in two places risks
them drifting (e.g., different index-to-id mapping) — a correctness-critical
detail since branch targets must resolve consistently everywhere.

## Decision 4: How the planner schema grows

**Decision**: Extend `WorkflowPlanner.plan()`'s existing JSON-array output format
in place — each step object may include `"id"`, `"branches"` (list of
`{"condition", "to"}`), and `"default_next"`, all optional. No new "graph mode" or
second planning method.

**Rationale**: Per FR-005/FR-012, a workflow with no conditional language must
still produce a plain linear plan — making branches a strictly optional field on
the same schema means the common case is untouched (same prompt shape, same
parse path) and the LLM only has to reach for the new fields when the description
actually calls for it, which keeps the "defaults to linear" requirement cheap to
satisfy.

**Alternatives considered**: A separate `plan_graph()` method with a distinct
schema, chosen by the caller based on whether the description "looks conditional."
Rejected: pushes a classification decision onto `create_workflow` (the caller)
before planning even starts, duplicates prompt/parsing logic, and creates two
code paths to keep behaviorally consistent for the plain-linear case instead of
one.

## Decision 5: Where branch/default-next target validation happens

**Decision**: Validate immediately after `planner.plan()` returns, inside
`create_workflow` (`agents/workflow/tools.py`) — check every `Branch.to` and
`default_next` against the set of step ids in the same plan (plus `"END"`/`"FAIL"`),
raising the existing `WorkflowPlanError` on the first invalid target found.

**Rationale**: `create_workflow` already wraps `planner.plan()` in a
`try/except WorkflowPlanError` that returns a user-facing `{"error": ...}` dict
(`tools.py:100-104`) — validation failures reuse that exact path with zero new
error-handling plumbing. Per FR-010, this must happen at creation/edit time, and
`create_workflow` is the only current entry point that persists a newly planned
workflow.

**Alternatives considered**: Validating inside `WorkflowStore.create()`. Rejected:
the store is a thin persistence `Protocol` with no knowledge of planning errors or
`WorkflowPlanError`; pushing domain validation into the storage layer would mix
concerns the codebase currently keeps separate (planner produces/validates
*meaning*, store persists *data*).

## Decision 6: How the UI decides "this workflow has branches" (FR-017)

**Decision**: Compute `const hasBranches = workflow.steps.some(s => s.branches.length > 0)`
client-side, in both `WorkflowStepsList` and `LiveRunPanel`, from the already-fetched
`WorkflowDetailResponse.steps`. No new API field, no server-computed flag.

**Rationale**: The data needed (each step's `branches` list) is already present on
the object both components already have in hand once FR-014's schema change
ships — computing a boolean from an array that's already loaded is strictly
simpler than adding a redundant server-computed field that could drift from the
underlying data. `default_next` alone (with empty `branches`) doesn't count as
"branching" for this purpose — a plain reordering override still has a fully
determined, fixed step count, so FR-017's condition is specifically "any step has
a non-empty `branches` list," not "any step has non-default routing."

**Alternatives considered**: A server-computed `workflow.has_branches: bool` field
on `WorkflowResponse`. Rejected: purely derived data with no independent meaning
or query pattern of its own — adding it to the schema would be state that has to
be kept in sync with `steps` for no benefit over computing it once, cheaply, where
it's used.
