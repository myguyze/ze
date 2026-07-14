# Feature Specification: Workflow Resilience and Control

**Feature Branch**: `107-workflow-resilience`

**Created**: 2026-07-14

**Status**: Implemented

**Input**: User description: "Workflow resilience and control — a phase covering: (1) retries for transient step failures (LLM/tool flake) before a step is declared failed; (2) per-step failure policy / criticality (e.g. on_failure: fail | continue | skip_to, or a critical: bool) so non-critical steps like monitoring/enrichment checks don't kill the whole run, building on the existing branches/default_next machinery; (3) partial-result synthesis — when a critical step does fail, workflow_failed should still synthesize and deliver the successful steps' output instead of discarding it; (4) 'no results found' should not automatically count as step failure for search/monitoring-shaped steps — verify_step and the planner's verify-criteria authoring need to distinguish 'step malfunctioned' from 'step legitimately found nothing'; (5) step editing — update_workflow currently only changes the schedule; users need to edit individual step definitions (task, verify criteria, branches) without deleting and recreating the whole workflow; (6) run cancellation — trigger_now is fire-and-forget with no way to cancel an in-flight execution. Scope note: this follows a separate bug-fix PR (already implemented) that fixed failure-alert wiring, scheduler overlap prevention, stale-run recovery, and step duration tracking — this phase is purely the resilience/control feature work, not those bugs."

## Clarifications

### Session 2026-07-14

- Q: Which step failure-policy model should this phase implement — `critical: bool` only, full `on_failure` enum, or both? → A: Full `on_failure` policy (`fail`, `continue`, or `skip_to:<step_id>`); no separate critical flag.
- Q: Which user-facing surfaces should deliver step editing and run cancellation? → A: REST API + workflow agent tools; ze-web gets a cancel button only (no step-editing UI this phase).
- Q: What is the system default maximum retry count per step? → A: 2 retries (3 total attempts); system default, not user-configurable this phase.
- Q: When every step has `on_failure: continue` and all steps fail, what is the overall run status? → A: `failed` — no step succeeded; execution still reaches the end and delivers a failure summary listing each step's failure.
- Q: Where should partial-result synthesis be delivered when a run fails after partial progress? → A: Existing workflow failure notification path (push alert + run-history summary).
- Q: Should step editing include definition snapshots for historical runs? → A: Yes — persist `steps_snapshot` on each execution at start; historical UI renders snapshot + explicit labels when definition differs from current workflow. Full revision history remains out of scope.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resilient steps don't kill the whole run (Priority: P1)

A user has a scheduled monitoring workflow with several steps: some are essential (compile and deliver a report), others are exploratory (check for brand-new developments that may or may not exist). Today, if an exploratory step finds nothing and its verification fails, the entire run is marked failed and none of the essential steps' output is ever delivered — even though most of the workflow actually succeeded.

**Why this priority**: This is the exact failure mode the user already hit in production (a monitoring workflow died on a step that legitimately found nothing new). It is the highest-leverage fix: it directly restores value from runs that are currently thrown away, and it's a prerequisite for stories 2–4 to matter.

**Independent Test**: Create a workflow where one step has `on_failure: continue` and fails; verify the run still completes and reaches the steps after it (or the branch designated for that outcome), rather than the whole run being marked failed.

**Acceptance Scenarios**:

1. **Given** a workflow step with `on_failure: continue`, **When** that step fails verification, **Then** the workflow continues to the next step instead of failing the whole run.
2. **Given** a workflow step with `on_failure: skip_to:<step_id>`, **When** that step fails verification, **Then** the workflow jumps to the designated step rather than failing the whole run.
3. **Given** a workflow step with `on_failure: fail` (or left at the default), **When** that step fails verification, **Then** the workflow still fails as it does today.
4. **Given** a step with a non-fail `on_failure` policy that fails, **When** the run later completes, **Then** the failure is recorded in the run's history so the user can see that step didn't succeed, even though the run overall succeeded.

---

### User Story 2 - Partial results are delivered when a run does fail (Priority: P2)

A user's workflow has a critical step that fails partway through (e.g., a tool error). Earlier steps already produced useful output — research findings, a partial report — but today that work is discarded and the user only sees an error message.

**Why this priority**: Directly recovers value from runs that are correctly (not incorrectly) marked as failed. It's the second-highest-value fix because it applies to every workflow failure, not just monitoring-shaped ones, and requires no new authoring effort from the user.

**Independent Test**: Trigger a workflow where step 1 succeeds and step 2 (critical) fails; verify the delivered failure notification/report includes a synthesis of step 1's output alongside the failure explanation, not just the bare error.

**Acceptance Scenarios**:

1. **Given** a workflow where a step with `on_failure: fail` fails after one or more prior steps succeeded, **When** the run is marked failed, **Then** the user receives a summary of the successful steps' output in the existing failure notification (push alert and run history), in addition to the failure reason.
2. **Given** a workflow whose very first step fails, **When** the run is marked failed, **Then** the user receives the failure reason only (no partial summary is fabricated when there's nothing to summarize).

---

### User Story 3 - Transient glitches don't fail a whole run (Priority: P3)

A user's scheduled workflow occasionally fails because of a one-off issue — a slow response, a temporary rate limit — that would have succeeded if attempted again a moment later. Today there is no retry; a single flaky call fails the entire scheduled run and the user gets an unnecessary failure alert.

**Why this priority**: Reduces false-positive failures and alert noise, but the volume of transient failures is lower than the "no results" and partial-loss cases addressed by P1/P2, so it ranks below them.

**Independent Test**: Simulate a step whose underlying call fails once and succeeds on a second attempt; verify the step is retried automatically and the run completes successfully without the user having to intervene.

**Acceptance Scenarios**:

1. **Given** a step's execution fails in a way considered transient, **When** the step is retried within its retry limit, **Then** a subsequent successful attempt allows the run to proceed normally.
2. **Given** a step that fails on every retry attempt, **When** the retry limit is exhausted, **Then** the step is declared failed and existing failure handling (criticality, alerts) applies as normal.
3. **Given** a step that is retried, **When** the run completes, **Then** the run history reflects that a retry occurred (so the user can distinguish "worked first try" from "needed a retry").

---

### User Story 4 - "Nothing new to report" isn't treated as a failure (Priority: P4)

A user has a monitoring-style workflow step whose job is to check for new developments on a topic. When there genuinely is nothing new, the step should be recorded as a successful check with an empty/negative finding — not as a failed step. Today, the verification step and the guidance given to whoever authors these workflows both treat "no results" the same as "something went wrong."

**Why this priority**: This addresses the root cause behind Story 1's symptom for the common "monitoring" workflow shape, but is lower priority than the general mechanism in Story 1 because Story 1 already provides a manual escape hatch (`on_failure: continue`) that covers the same real-world case.

**Independent Test**: Create a monitoring-shaped step whose criteria explicitly allows "no new items found" as a valid outcome; run it against a source with nothing new; verify the step is recorded as successful with a "nothing new" finding, not as failed.

**Acceptance Scenarios**:

1. **Given** a step intended to check for new/breaking information, **When** the check completes successfully but finds nothing new, **Then** the step is recorded as successful with that finding, not as failed.
2. **Given** a step that fails to even perform its check (e.g., the underlying search errors out), **When** verification runs, **Then** the step is still recorded as failed — "found nothing" and "couldn't look" remain distinguishable outcomes.
3. **Given** a newly authored workflow whose steps are monitoring-shaped, **When** the workflow is created, **Then** the authored verification criteria for those steps already account for "no new results" as an acceptable outcome, without the user having to manually specify this.

---

### User Story 5 - Editing a workflow step without rebuilding the workflow (Priority: P5)

A user wants to tweak one step of an existing workflow — loosen its verification criteria, reword its task, or change its branching — without losing the workflow's run history or having to delete and recreate it from scratch.

**Why this priority**: A usability gap that blocks users from applying the very kind of tuning this phase enables (e.g., "set this step's on_failure to continue," "relax this step's criteria"). Ranked below the resilience mechanics themselves because a user can still work around it today by recreating the workflow, just with friction and lost history.

**Independent Test**: Edit a single step's task text on an existing scheduled workflow via chat or REST API and verify the next scheduled run uses the updated step while the workflow's prior run history remains intact.

**Acceptance Scenarios**:

1. **Given** an existing workflow, **When** a user edits one of its steps (task, verification criteria, branches, or `on_failure` policy), **Then** the change is saved and takes effect on the next run without affecting the workflow's schedule or history.
2. **Given** an existing workflow, **When** a user adds, removes, or reorders steps, **Then** the workflow reflects the new step list on its next run.
3. **Given** an edit that would leave a branch pointing at a step that no longer exists, **When** the user attempts to save it, **Then** the system rejects the edit and explains why, rather than silently saving a broken workflow.

---

### User Story 6 - Cancelling a run that's already in progress (Priority: P6)

A user manually triggers a workflow and then realizes it shouldn't be running right now (wrong timing, stale inputs, or it's just going to burn time/cost on something no longer needed). Today there is no way to stop it once started — the user has to wait for it to finish or fail on its own.

**Why this priority**: Valuable for cost and control, but affects a narrower moment (mid-flight, user-triggered runs) than the other stories, and users have a passive workaround (just wait it out) that doesn't exist for the other gaps.

**Independent Test**: Trigger a workflow run from the web UI, then request cancellation via the cancel button (or REST/agent tool) while it's mid-execution; verify the run stops promptly and is recorded with a distinct "cancelled" outcome rather than "completed" or "failed."

**Acceptance Scenarios**:

1. **Given** a workflow run that is currently in progress, **When** the user requests cancellation, **Then** the run stops before completing further steps and is marked as cancelled.
2. **Given** a workflow run that has already finished (successfully or not), **When** the user requests cancellation, **Then** the system reports that there is nothing to cancel rather than taking a destructive or confusing action.
3. **Given** a cancelled run, **When** the user reviews run history, **Then** the run is clearly distinguishable from completed and failed runs, including whatever partial output existed at the moment of cancellation.

---

### User Story 7 - Historical runs stay faithful after edits (Priority: P5b)

A user edits a workflow's steps and then opens an older run from before the edit. The run should show the step graph and step metadata **as they were when that run started**, not the current live definition — and the UI should make that explicit so the user is never misled into thinking an old run used today's steps.

**Why this priority**: Step editing (Story 5) is unsafe to rely on without this; overlaying old `step_results` on the current graph produces incorrect history. Tied to editing, not a separate product feature.

**Independent Test**: Edit a workflow (rename/remove a step), then select a pre-edit execution; verify the graph matches the pre-edit definition and the UI states that the run used an older definition.

**Acceptance Scenarios**:

1. **Given** a workflow that has been edited since a past run, **When** the user selects that past run, **Then** the graph and step detail panel render from the run's persisted `steps_snapshot`, not the workflow's current steps.
2. **Given** a past run whose snapshot differs from the current workflow definition, **When** the user views that run, **Then** the UI displays an explicit notice that the workflow has been edited since this run (including the run's start time).
3. **Given** no execution is selected (or a live run using the current definition), **When** the user views the workflow detail page, **Then** the graph shows the **current** workflow definition with a clear "Current definition" label.
4. **Given** a legacy execution with no `steps_snapshot` (created before this feature), **When** the user selects it, **Then** the UI shows a fallback notice that the definition at run time is unavailable and the graph may not match what actually ran.

---

### Edge Cases

- What happens when every step in a workflow has `on_failure: continue` and all of them fail? The run MUST still reach the end, be marked **`failed`** (because no step succeeded), and deliver a summary listing each step's failure — not silently appear successful with no content.
- What happens when a step with `on_failure: continue` fails on the path that a later step with `on_failure: fail` depends on (e.g., step B needs step A's output, but A failed and continued)? The dependent step's own verification is expected to catch and fail on missing/inadequate input, so this remains within existing behavior rather than requiring new handling.
- What happens when a retryable step keeps hitting the retry limit on every scheduled run indefinitely? This should surface the same way persistent failures already do (via existing failure alerting), just after the retry attempts are exhausted each time.
- What happens if a user cancels a run at the exact moment the very last step is completing? The system should resolve to whichever outcome (cancelled vs. completed) reflects what work actually finished — no run should be left in an ambiguous or stuck state.
- What happens when a user edits a step that a currently in-progress run has already started executing? The in-progress run continues using the step definitions it started with; the edit applies starting from the next run.
- What happens when a user views a historical run after reordering or removing steps? The UI MUST render the run's `steps_snapshot`; step results for removed step ids may still appear in the execution list even if those nodes are absent from a current-definition graph.

## Requirements *(mandatory)*

### Functional Requirements

**Retries**

- **FR-001**: System MUST automatically retry a step's execution when it fails for a reason considered transient, up to a bounded number of attempts, before declaring the step failed.
- **FR-002**: System MUST NOT retry indefinitely — each step MUST have a maximum retry count after which it is declared failed and normal failure handling applies. The system default is **2 retries (3 total attempts per step)**; this default is not user-configurable per step in this phase.
- **FR-003**: System MUST record, per step result, whether a retry occurred and how many attempts were made, visible in run history.

**Step failure policy (`on_failure`)**

- **FR-004**: Each workflow step MUST have an `on_failure` policy with exactly one of: `fail` (end the run), `continue` (proceed to the next step in order), or `skip_to:<step_id>` (jump to a designated step). There is no separate `critical` flag — `fail` is the default and preserves today's behavior.
- **FR-005**: System MUST default a step's `on_failure` policy to `fail` when not explicitly set, preserving today's behavior for workflows that don't opt in.
- **FR-006**: When a step with `on_failure: continue` fails, system MUST proceed to the next step in order rather than ending the run.
- **FR-007**: When a step with `on_failure: skip_to:<step_id>` fails, system MUST jump to the designated step (reusing existing step-routing machinery) rather than ending the run.
- **FR-008**: System MUST record a failed step's outcome in the run's history even when `on_failure` is `continue` or `skip_to` and the run as a whole continues and may ultimately succeed.
- **FR-009**: When a step with `on_failure: fail` fails, system MUST end the run as failed (no change from current behavior).
- **FR-009a**: When a run reaches the end with at least one successful step (including mixed outcomes where some `on_failure: continue` steps failed), system MUST mark the run **`completed`** and record per-step failures in run history.
- **FR-009b**: When a run reaches the end with **zero** successful steps (e.g., every step failed but all had `on_failure: continue`), system MUST mark the run **`failed`** and deliver a summary of all step failures.

**Partial-result synthesis**

- **FR-010**: When a run ends in failure after at least one step has already succeeded, system MUST synthesize and include the successful steps' output in the failure report delivered to the user via the **existing workflow failure notification path** (push alert and run-history `summary` field).
- **FR-011**: When a run fails before any step has produced usable output, system MUST deliver the failure reason via the same notification path without fabricating a partial summary.

**"No results" vs. "couldn't look" verification semantics**

- **FR-012**: System MUST distinguish between a step that performed its task and found no relevant/new results, and a step that failed to perform its task at all (e.g., an underlying error) — the former MUST NOT automatically count as a step failure.
- **FR-013**: When authoring a new workflow whose steps are shaped as ongoing monitoring/checking, the system MUST author verification criteria that accept "nothing new found" as a valid, successful outcome by default.
- **FR-014**: Step results MUST record whether a "no results" outcome occurred, distinguishable from other successful outcomes and from failures, so it is visible in run history and any delivered summary.

**Step editing**

- **FR-015**: Users MUST be able to edit an existing workflow's individual steps (task description, verification criteria, branches, and `on_failure` policy) without deleting and recreating the workflow — via REST API and workflow agent tools (chat).
- **FR-016**: Users MUST be able to add, remove, or reorder steps on an existing workflow — via REST API and workflow agent tools (chat).
- **FR-017**: System MUST validate step edits before saving — at minimum, rejecting a save that leaves a branch, default-next target, or `skip_to` target pointing at a step id that doesn't exist in the edited step list.
- **FR-018**: Editing a workflow's steps MUST preserve the workflow's existing schedule and past execution records. "Preserve history" means execution rows and their snapshots are immutable; only the live workflow definition changes.
- **FR-018b**: When an execution starts, the system MUST persist a `steps_snapshot` (full step list JSON, same shape as `workflows.steps`) on the execution record, capturing the definition used for that run.
- **FR-018c**: Step edits MUST NOT modify `steps_snapshot` on existing or in-progress executions.
- **FR-018d**: When displaying a historical execution in ze-web, the system MUST render the workflow graph and step metadata from that execution's `steps_snapshot`, not from the workflow's current steps.
- **FR-018e**: When a historical execution's `steps_snapshot` differs from the workflow's current steps (by deep comparison or version counter), ze-web MUST show an explicit, user-visible notice that the workflow has been edited since that run (e.g. banner above the graph: "This run used the workflow as it was on {started_at}. The definition has changed since then.").
- **FR-018f**: When no execution is selected, ze-web MUST label the graph as showing the **current** workflow definition (e.g. "Current definition").
- **FR-018g**: When a legacy execution has no `steps_snapshot`, ze-web MUST show an explicit fallback notice that the definition at run time is unavailable and the graph may not reflect what ran; it MUST NOT silently overlay results on the current graph without that warning.
- **FR-019**: A workflow edit MUST take effect starting with the next run triggered after the edit is saved; a run already in progress at the time of the edit MUST run to completion using the step definitions it started with.
- **FR-019a**: Step-editing UI on the workflow detail page in ze-web is **out of scope** for this phase; the web client remains read-only for step definitions (edits via REST/chat only).

**Run cancellation**

- **FR-020**: Users MUST be able to request cancellation of a workflow run that is currently in progress — via REST API, workflow agent tool (chat), and a cancel button on the workflow detail page in ze-web.
- **FR-021**: System MUST stop executing further steps of a run once cancellation is requested and record the run with a distinct "cancelled" status (not "completed" or "failed").
- **FR-022**: Requesting cancellation of a run that has already finished MUST be a no-op that clearly informs the user there was nothing to cancel, rather than silently failing or affecting a different run.
- **FR-023**: A cancelled run's history MUST retain whatever step results were produced before cancellation, so the user can see how far it got.

### Key Entities *(include if feature involves data)*

- **Workflow Step**: An individual unit of work within a workflow. Gains new attributes for this phase: `on_failure` (`fail` | `continue` | `skip_to:<step_id>`, default `fail`). Retries use a system-wide default of 2 retries (3 total attempts), not a per-step setting in this phase.
- **Step Result**: The recorded outcome of one step's execution within a run. Gains new attributes for this phase: retry count, and whether the outcome was a "no results found" success versus another kind of success or failure.
- **Workflow Execution (Run)**: A single execution of a workflow. Gains a new possible status, "cancelled," alongside the existing running/completed/failed statuses. Gains `steps_snapshot`: the immutable step-definition list frozen at execution start (107b follow-up).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Workflow runs that would previously have failed solely because of a step with `on_failure: continue` now complete and deliver their remaining output — measured by a reduction in "whole run failed" outcomes for workflows using non-fail `on_failure` policies.
- **SC-002**: When a run does fail after partial progress, the user receives the successful steps' output in the existing failure notification (push alert and run history) in 100% of such cases.
- **SC-003**: At least a meaningful share of previously-failing transient errors (e.g., one-off timeouts) now resolve successfully via retry without any user action, reducing unnecessary failure alerts.
- **SC-004**: For monitoring-shaped workflow steps, "nothing new found" no longer produces a failure outcome — verified by re-running the specific scenario that previously caused a false failure and confirming it now completes successfully.
- **SC-005**: Users can adjust a single workflow step (e.g., relax its criteria or set `on_failure: continue`) in one edit action via chat or REST API, without recreating the workflow or losing its run history.
- **SC-006**: Users can stop an in-progress run within a few seconds of requesting cancellation from the web UI, chat, or REST API, and the run is unambiguously recorded as cancelled.
- **SC-007**: After editing a workflow, opening a pre-edit execution shows the pre-edit step graph from `steps_snapshot` and an explicit UI notice that the definition has changed since that run — verified by edit → re-open historical run test (quickstart.md Story 7).

## Deferred / out of scope

- Full workflow **revision history** (list of past definitions, diff, rollback to vN) — future phase if needed.
- **`definition_version` counter** on the workflow row — optional follow-up for badges; not required if snapshot comparison suffices.
- Step-editing UI on the workflow detail page — still out of scope (FR-019a); only snapshot **display** and notices are in scope for 107b.

## Assumptions

- This phase builds directly on the existing branch/default_next step-routing machinery; `on_failure: continue` and `on_failure: skip_to:<step_id>` reuse that mechanism rather than introducing a separate routing system. There is no separate `critical` boolean — policy is expressed solely via `on_failure`.
- Retry behavior applies per-step, not to the workflow as a whole; a workflow is not restarted from scratch after a step-level retry exhausts its attempts. The system default is 2 retries (3 total attempts per step); per-step retry limits are not user-configurable in this phase.
- "Transient" failure classification is a reasonable default determined by the system (e.g., tool/LLM call errors) rather than something the user configures per step in this phase.
- The scope of this phase is triggered/scheduled workflow execution generally, not specific to any one domain (monitoring workflows are the motivating example, but the mechanisms are general-purpose).
- This phase assumes the separately-shipped bug fixes (failure-alert wiring, scheduler overlap prevention, stale-run recovery, step duration tracking) are already in place and does not re-address them.
- Cancellation is best-effort at step boundaries — a step already in flight when cancellation is requested is expected to finish that step before the run stops, rather than being forcibly interrupted mid-step.
- Step editing is exposed via REST API and workflow agent tools only; ze-web adds a cancel button for in-progress runs but does not add step-editing UI in this phase.
- Partial-result synthesis on failure uses the existing workflow failure notification path (push alert + run-history summary); no new delivery channel is introduced in this phase.
- Per-run `steps_snapshot` (107b) is definition pinning, not full versioning — one snapshot per execution, no separate revision table.
- Adding `steps_snapshot` and extending the `workflow_executions.status` CHECK constraint for `cancelled` requires a small Alembic migration (`zc025` in ze-automation chain); JSONB step fields on workflows remain migration-free.
