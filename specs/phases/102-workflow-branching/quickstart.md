# Quickstart: Validating Workflow Conditional Branching

Prerequisites: `make db-up && make migrate` (no new migration ships with this
feature, but a running Postgres is needed for `make dev`/tests as usual);
`make dev` running; a chat session against `ze-api`.

## 1. Branching behavior (User Story 1)

Ask Ze to create a workflow with an explicit either/or:

> "Create a workflow called 'invoice-check' that checks my inbox for an invoice
> from Acme; if one arrived, forward it to accounting@example.com, otherwise log
> that no invoice arrived today."

Inspect the result:

```
get_workflow("invoice-check")
```

Expected: the checking step's `"branches"` is non-empty (two entries — one
routing to the forward step, one routing to the log step); see
[data-model.md](./data-model.md) for the exact shape.

Trigger it twice (`trigger_workflow("invoice-check")`), once against inbox state
with a matching invoice and once without, and check
`list_workflow_executions("invoice-check")` after each run — the executed
`step_id` sequence should differ between the two runs, and each entry where a
branch fired should show `"branch_taken"` set to the matching condition text.

## 2. Backward compatibility (User Story 3)

Before implementing, capture a `SELECT steps FROM workflows LIMIT 1;` row from
an existing workflow (or construct one via the pre-feature code path in a test)
that has no `id`/`branches`/`default_next` keys in its stored JSON.

After implementing: load it via `get_workflow`, confirm `"branches": []` on
every step and ids present as `"s0"`, `"s1"`, ... in list order; trigger it and
confirm the run's `step_id` sequence matches the original list order exactly,
with identical pass/fail outcome to before the feature shipped (SC-002).

## 3. Loop guard (User Story 2)

Construct a workflow (directly via `WorkflowStore.create`, not natural-language
planning, to force a deterministic loop for the test) where step `s1`'s single
branch always routes back to `s1` itself. Trigger it and confirm:

- The run fails after the 4th execution of `s1` (1 initial + 3 revisits, per
  the FR-008 clarification).
- The failure message names the step and explains the loop limit was hit.
- `list_workflow_executions` shows exactly 4 `step_results` entries for `s1`,
  no more.

## 4. Planner behavior (User Story 4)

Two `WorkflowPlanner.plan()` calls, asserted directly in
`core/ze-automation/tests/workflow_engine/test_workflow_planner.py` (mocking
`LLMClient.complete` to return a fixed branching vs. linear JSON payload):

- A description with "if X then Y otherwise Z" phrasing → returned steps
  include at least one non-empty `branches` list.
- A plain sequential description → returned steps all have `branches == []`.

## 5. Existing Workflows screen stays accurate (User Story 5)

`make dev-full` (backend + `ze-web`), then in the browser:

1. Open the "invoice-check" workflow from step 1 above at
   `/workflows/{id}`. Confirm the run where the invoice was found shows only
   the forward-email step as completed, and the "log no invoice" step is not
   shown as part of that run — not greyed out as "pending forever," not shown
   as skipped-but-present, simply absent from that run's path (per FR-015).
2. Open the run from step 1's other trigger (no invoice found) and confirm the
   opposite: the log step shows completed, the forward step is absent.
3. Trigger the loop-guard workflow from step 3 above and open its (failed) run
   in the UI: confirm `s1` appears as **four separate rows**, each with its own
   output/expansion, not one row.
4. Open any pre-existing, non-branching workflow's run history and confirm the
   screen looks pixel-identical to before this feature shipped (SC-006's
   "zero visual regression" requirement).
5. On the "invoice found" run from step 1, confirm the skipped ("log no
   invoice") step shows dimmed with a "not taken this run" label — not a bare
   pending circle, not absent from the DOM (FR-016).

`LiveRunPanel` (shown while a run is actively in progress) needs the same checks
repeated live: trigger "invoice-check" and watch the panel while it runs,
confirming:
- The currently-highlighted row tracks the real execution path rather than
  static array position.
- The header shows a running count with **no denominator** ("Step 2…", not
  "Step 2 / 3") for the duration of the run, since this workflow has branches
  (FR-017).
- Triggering any pre-existing non-branching workflow still shows the fixed
  "Step N / total" form unchanged.

## Automated coverage

Run the full suite for the touched packages:

```bash
make test-automation   # core/ze-automation — types, planner, postgres store, rest.py
make test-personal     # plugins/ze-personal — graph executor (route_branch, loop guard)
make test-web          # ze-web — WorkflowStepsList/LiveRunPanel rendering-order unit tests
```

(See `docs/testing.md` for the exact `make test-<name>` target names if these
differ from the package directory names.)
