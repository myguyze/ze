# Quickstart: Validating Workflow Resilience and Control

## Prerequisites

```bash
make db-up
make migrate          # no new migrations this phase
make dev-full         # backend + web, or `make dev` for API only
```

Existing workflows without `on_failure` in step JSON behave as today (default
`fail`). No config.yaml changes required.

## Story 1 — `on_failure: continue` keeps the run alive

1. Create or edit a workflow with two steps; set step 1 `on_failure: "continue"`
   and verify criteria guaranteed to fail; step 2 should succeed.
2. Trigger via chat (`trigger_workflow`) or `POST /api/v0/workflows/{id}/trigger`.
3. Expect: execution status `completed`; step 1 in history with `success: false`;
   step 2 executed; no workflow failure push alert.

Via REST edit:

```bash
curl -X PATCH "$ZE/api/v0/workflows/$WF_ID/steps" \
  -H "Authorization: Bearer $ZE_API_KEY" \
  -H "Content-Type: application/json" \
  -d @fixtures/continue-on-failure-steps.json
```

## Story 2 — Partial results on failure

1. Workflow: step 1 succeeds; step 2 has `on_failure: fail` and fails.
2. Trigger run.
3. Expect: status `failed`; push notification body includes synthesized output
   from step 1 (not just the error string); run history `summary` populated.

## Story 3 — Transient retry

1. Unit test path (no live flake needed):

```bash
make test-personal   # graph retry routing tests
make test-automation
```

2. Integration: mock agent to fail once with timeout-like error, succeed on
   second attempt — expect `step_results[].attempt_count == 2` and run
   `completed`.

## Story 4 — "Nothing new" is success

1. Monitoring-shaped workflow with verify criteria allowing empty findings.
2. Run against a topic with no new items.
3. Expect: step `success: true`, `no_results: true`; run completes without
   failure alert.

## Story 5 — Edit steps without recreating workflow

1. `PATCH /api/v0/workflows/{id}/steps` or chat: "set the monitoring step's
   on_failure to continue".
2. Confirm next run uses updated steps; prior executions unchanged in
   `GET …/executions`.

Validation rejection:

```bash
# Expect 422 — branch points at removed step id
curl -X PATCH ... -d '{"steps":[{"id":"s0","task":"…","branches":[{"condition":"x","to":"s99"}]}]}'
```

## Story 6 — Cancel in-progress run

1. Open `/workflows/{id}` in ze-web; trigger a long-running workflow.
2. Click **Cancel** (visible while status is `running`).
3. Expect within a few seconds: status `cancelled`; partial step results
   retained; no further steps after current boundary.

REST equivalent:

```bash
curl -X POST "$ZE/api/v0/workflows/$WF_ID/executions/$EXEC_ID/cancel" \
  -H "Authorization: Bearer $ZE_API_KEY"
```

Second cancel call returns `"status": "not_running"`.

## Regression checks

```bash
make test-automation
make test-personal
make test-api
make lint
```

Existing workflows (no `on_failure` key) MUST still fail the whole run on step
failure — verify with a legacy two-step workflow test case in
`plugins/ze-personal/tests/graph/test_workflow.py`.

## All-fail continue edge case (FR-009b)

1. Two-step workflow; both `on_failure: continue`; both fail verification.
2. Expect: status `failed` (not `completed`); summary lists both failures.
