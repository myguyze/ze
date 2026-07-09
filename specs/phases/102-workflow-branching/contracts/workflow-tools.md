# Contracts: Workflow Agent Tools

Ze has no public HTTP API for workflows — workflows are authored and inspected
entirely through `@tool`-decorated functions in
`core/ze-automation/ze_automation/agents/workflow/tools.py`, called by the
`WorkflowAgent` (LLM-driven ReAct loop) or a user's chat turn. Those tool
signatures/return shapes are the effective "interface contract" this feature
touches. No REST/WS endpoint changes.

## `create_workflow` — behavior change

**Before**: plans steps, extracts schedule, persists, schedules. Only failure
mode is `WorkflowPlanError` from planning/schedule-parsing.

**After**: same flow, plus a validation pass on the planned steps before
persisting:

```
steps = await planner.plan(description)
_validate_step_targets(steps)   # NEW — raises WorkflowPlanError on bad target
schedule = await planner.extract_schedule(...)
...
```

- **Input**: unchanged (`workflow_name: str`, `description: str`,
  `schedule_description: str = ""`).
- **Output on success**: unchanged shape — `{"name", "steps", "schedule"}`. May
  optionally include branch info in a future UI-facing iteration; not required
  by this spec's FR set.
- **Output on failure**: unchanged shape — `{"error": str}`. The error message
  for an invalid target follows the same phrasing style as existing plan errors,
  e.g. `"Couldn't plan the workflow: step 's2' branches to unknown step 's9'"`.
- **New failure case**: a planned step's `branches[*].to` or `default_next`
  refers to a step id not present in the same plan (and isn't `"END"`/`"FAIL"`).
  Rejected before `store.create()` is ever called — no partially-invalid
  workflow is ever persisted (FR-010).

## `get_workflow` — output change

**Before**: `"steps"` is `[{"task", "agent_hint", "intent"}, ...]`.

**After**: each step dict gains `"id"`, `"branches"` (list of
`{"condition", "to"}`), and `"default_next"`, so an LLM inspecting a workflow (or
a human reading tool output) can see its branching structure. Steps with no
branches show `"branches": []` and `"default_next": null` — indistinguishable
from a pre-existing linear workflow's steps, by design (FR-011).

## `list_workflow_executions` — output change

**Before**: each execution's `"step_results"` entries are
`{"step_index", "task", "output", "success", "error", "duration_ms"}`.

**After**: each entry gains `"step_id"` and `"branch_taken"` (nullable), so a
caller can reconstruct which path a run took (FR-013) directly from this tool's
existing output — no new tool is introduced for this.

## Unaffected tools

`list_workflows`, `update_workflow`, `enable_workflow`, `disable_workflow`,
`delete_workflow`, `trigger_workflow` — no signature or output shape changes.
