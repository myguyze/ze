# Feature Specification: Workflow Conditional Branching

**Feature Branch**: `102-workflow-branching`

**Created**: 2026-07-09

**Status**: Implemented

**Input**: User description: "Add conditional branching and bounded looping to the workflow engine. Currently a Workflow is a flat list of WorkflowStep executed strictly in order, with a single verify-gate per step that either advances to the next step or fails the whole run. This spec should cover: giving each step a stable id; adding an optional list of branches (condition, target) on a step so it can route to a different step (or end/fail) based on a classification of the step's output, falling back to sequential order when no branches are defined; a default-next override; a bounded loop guard to allow a branch to point backward to an earlier step without risking infinite execution; extending workflow planning to optionally emit branches (defaulting to linear when not needed); and backward compatibility with existing saved workflows. Parallel execution of multiple steps at once is explicitly out of scope — that is a separate future feature. The motivation is unlocking conditional logic (if/else, switch-like branching) for workflows like 'check inbox, if invoice found do X else do Y', and eventually a visual graph-based view of a workflow, though that view is not part of this spec."

## Clarifications

### Session 2026-07-09

- Q: SC-005 says explicit conditional language should produce a branching workflow "in the large majority of cases tested" — what threshold should this be held to? → A: At least 90% of test cases with explicit conditional language produce a branching workflow.
- Q: FR-008's loop guard stops a run once a step is "revisited more than 3 times" — does the limit count total executions of the step, or revisits on top of the first normal visit? → A: Initial visit plus 3 revisits (4 total executions) before the next revisit fails the run.
- Q: User Story 5 says a skipped branch step must be "visibly not part of that run" — should the Workflows screen omit that step's row entirely, or show it visually marked as not taken? → A: Show it, visually distinguished (e.g. dimmed, labeled "not taken this run") rather than as pending/failed.
- Q: The live-run progress indicator today shows a fixed "Step N / total" count — what should it show once total step count on the actual path isn't knowable until a branching/looping run resolves? → A: Drop the fixed denominator for such runs; show a running step count only (e.g. "Step 3…"), no fabricated total.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Branch a workflow on step outcome (Priority: P1)

A user describes a workflow in natural language that includes a conditional ("if an invoice email arrived, forward it to accounting; otherwise, log that none was found"). When the workflow runs, the step that checks for the invoice produces an outcome, and the workflow automatically continues down the path that matches — without the user having to write two separate workflows or manually pick a path.

**Why this priority**: This is the entire point of the feature. Without it, conditional workflows either fail outright when the "wrong" branch's assumption doesn't hold, or the user has to pre-guess a single fixed sequence that only works for one of the possible outcomes.

**Independent Test**: Create a workflow with one branching step and two possible continuations; run it twice with inputs that force each outcome; verify each run completes via the correct path and produces the correct result, with the other path's steps never executed.

**Acceptance Scenarios**:

1. **Given** a workflow step with two branches ("invoice found" → step A, "no invoice found" → step B), **When** the step's output indicates an invoice was found, **Then** the workflow proceeds to step A and never executes step B.
2. **Given** the same workflow, **When** the step's output indicates no invoice was found, **Then** the workflow proceeds to step B and never executes step A.
3. **Given** a workflow step with no branches defined, **When** it completes successfully, **Then** the workflow proceeds to the next step in its original order, exactly as it does today.

---

### User Story 2 - Repeat a step until a condition is met, safely (Priority: P2)

A user describes a workflow that should retry or repeat a step until some condition holds (e.g., "keep checking every source until you find an answer, then summarize"). A branch can point back to an earlier step to create this repetition, but the workflow will never loop forever — it gives up and reports a clear failure after a bounded number of repeats.

**Why this priority**: Looping is a natural extension of branching (a branch target can be an earlier step) and is required for workflows that need retry-until-success behavior, but it introduces a new failure mode (infinite execution) that must be capped from day one, not bolted on later.

**Independent Test**: Create a workflow where a branch always routes back to an earlier step; run it; verify the workflow stops itself after a fixed number of repeats of that step and reports a clear "loop limit exceeded" failure rather than running indefinitely.

**Acceptance Scenarios**:

1. **Given** a workflow step whose branch points back to an earlier step, **When** the run revisits that earlier step more times than the configured limit, **Then** the workflow stops and reports a failure that names the step and explains the loop limit was hit.
2. **Given** the same workflow, **When** a branch eventually routes forward instead of looping again (before the limit is hit), **Then** the workflow continues normally past the loop.

---

### User Story 3 - Existing workflows keep working unchanged (Priority: P1)

A user who already has scheduled, recurring workflows created before this feature existed should see zero behavior change and zero manual migration effort. Their workflows keep running exactly as before.

**Why this priority**: This is a live system with already-scheduled workflows. Any change that requires re-creating or breaks existing workflows is unacceptable, and this must be validated alongside the new capability, not as an afterthought.

**Independent Test**: Take a workflow that was created and saved before this feature shipped, run it after the feature ships, and confirm it executes every step in its original order with no new prompts, errors, or behavior differences.

**Acceptance Scenarios**:

1. **Given** a workflow saved before this feature existed, **When** it is loaded after the feature ships, **Then** it runs its steps in the same order as before with no branching behavior applied.
2. **Given** the same pre-existing workflow, **When** it fails a step, **Then** the whole run fails exactly as it did before this feature — no new implicit branching or retry occurs where none was defined.

---

### User Story 4 - Workflow authoring can optionally describe branches (Priority: P3)

When a user describes a new workflow that contains conditional language, the system that turns the description into a runnable workflow is able to produce a workflow with branches rather than forcing everything into a single straight-line guess. When the description is simple and linear, it continues to produce a plain sequential workflow as it does today.

**Why this priority**: Branching is only useful if workflows can actually be authored with it. This is lower priority than the execution mechanics (Stories 1–3) because a branching workflow could initially be hand-constructed for testing, but it's required for the feature to be usable end-to-end by a normal user.

**Independent Test**: Submit a workflow description containing an explicit conditional ("if X do A else do B") and confirm the resulting workflow has a branching step; submit a simple linear description and confirm the resulting workflow has no branches.

**Acceptance Scenarios**:

1. **Given** a workflow description with an explicit either/or condition, **When** the workflow is generated, **Then** the resulting workflow contains a step with branches representing both outcomes.
2. **Given** a workflow description with no conditional language, **When** the workflow is generated, **Then** the resulting workflow contains no branches and runs linearly.

---

### User Story 5 - The existing Workflows screen stays accurate for branching and looping runs (Priority: P1)

Ze already has a Workflows screen showing each workflow's steps and, per run, which steps completed, which failed, and which is currently running. This view already exists and is used today for every scheduled workflow. When a workflow now branches or loops, this same screen must keep showing an accurate picture of what actually happened — the step that ran, in the order it ran, including a step that was skipped because a different branch was taken, and a step that ran more than once because of a loop.

**Why this priority**: This is not a new feature request — it's a correctness requirement created by this spec. The existing screen was built assuming a workflow always executes its steps in one fixed order, one time each. Branching and looping break that assumption. Shipping branching/looping without fixing this would make an already-live screen show a misleading or incomplete picture of what a workflow actually did — the wrong step highlighted as "in progress," or a repeated loop step invisible after its first run.

**Independent Test**: Run a branching workflow where one of two steps is skipped; open its run in the existing Workflows screen and confirm only the step that actually ran is shown as completed, and the skipped step is visibly not part of that run. Run a looping workflow that revisits one step three times; confirm the screen shows three separate entries for that step, not one.

**Acceptance Scenarios**:

1. **Given** a completed run of a branching workflow where step B was skipped in favor of step C, **When** a user views that run in the Workflows screen, **Then** step C appears as completed and step B is shown visually distinguished as "not taken this run" — not shown as pending, failed, or completed.
2. **Given** a completed run of a looping workflow where one step executed four times before continuing, **When** a user views that run, **Then** the screen shows four distinct entries for that step, each with its own output, not one entry silently overwritten by the others.
3. **Given** a workflow with no branches (today's linear case), **When** a user views any of its runs, **Then** the screen looks and behaves exactly as it does today, including the fixed "N / total" live progress indicator.
4. **Given** a branching workflow's run in progress, **When** a user views the live progress indicator, **Then** it shows a running step count with no fixed total (e.g. "Step 3…"), not a fabricated or misleading denominator.

### Edge Cases

- What happens when a step's output doesn't clearly match any defined branch condition? The workflow falls back to the step's default next step (or plain sequential order if no default is set) rather than failing outright.
- What happens when a branch target refers to a step id that doesn't exist in the workflow (e.g., due to a bad edit or a planning error)? The workflow is rejected as invalid before it is ever run, with an error identifying the missing target.
- What happens when a step fails (its own verification fails) before branching is even evaluated? The existing failure behavior takes precedence — a failed step still fails the run; branch evaluation only happens on successful step output.
- What happens when a loop is created without eventually reaching a failure or forward branch? The bounded loop guard (User Story 2) catches this and terminates the run with a clear error rather than running forever.
- What happens when two branch conditions on the same step could both plausibly match the step's output? Branch conditions are evaluated in the order they're defined, and the first matching condition wins.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every workflow step MUST have a stable identifier that is unique within its workflow, usable as a branch target.
- **FR-002**: A workflow step MUST support an optional ordered list of branches, each pairing a natural-language condition with a target (another step's identifier, or a terminal "end the workflow" / "fail the workflow" outcome).
- **FR-003**: After a step completes successfully, if it has branches defined, the system MUST evaluate the step's output against each branch condition in order and route to the first matching branch's target.
- **FR-004**: If a step has branches defined but none of them match the step's output, the system MUST fall back to that step's default next step if one is set, or to plain sequential order otherwise.
- **FR-005**: If a step has no branches defined, the system MUST continue to advance to the next step in sequential order, identical to current behavior.
- **FR-006**: A step MUST support an optional default-next override that takes precedence over plain sequential order when no branch matches (or when the step has no branches at all but authoring wants to skip ahead or jump to a specific step).
- **FR-007**: The system MUST allow a branch target to be an earlier step in the same workflow (a loop) without treating this as invalid at workflow-save time.
- **FR-008**: The system MUST track, per run, how many times each step has been (re-)entered via looping, and MUST stop the run with a descriptive failure once a step's total execution count within that run exceeds 1 (initial visit) plus a fixed configured revisit limit (default: 3 revisits, i.e. 4 total executions).
- **FR-009**: A step failure (its own success/verification check failing) MUST fail the whole run exactly as it does today; branch evaluation only occurs after a successful step.
- **FR-010**: The system MUST validate, at the time a workflow is created or edited, that every branch target and default-next value refers either to an existing step identifier in that workflow or to one of the terminal outcomes ("end", "fail"). Workflows with invalid targets MUST be rejected with an error naming the invalid target.
- **FR-011**: Workflows created before this feature existed MUST continue to run correctly without modification: step identifiers are assigned automatically to any step that lacks one, and the absence of branches on every step MUST preserve today's linear execution behavior exactly.
- **FR-012**: The system that generates workflows from a natural-language description MUST be able to produce steps with branches when the description implies a conditional outcome, and MUST continue to produce plain linear workflows when it does not.
- **FR-013**: The record of a completed or failed run MUST show which path was actually taken through the workflow (including which branch fired at each branching step), so a user can see after the fact why the run went the way it did.
- **FR-014**: Every interface that currently exposes a workflow's steps or a run's results (both the natural-language agent tools and the existing Workflows screen's read API) MUST be updated to expose step identifiers, branches, and default-next targets, and to expose which step identifier and which branch (if any) each run result corresponds to. Interfaces MUST NOT drop or hide this information for workflows that use branching.
- **FR-015**: The existing Workflows screen's step-by-step run view MUST render a run's steps in the order they actually executed (including repeated entries for a looped step) rather than assuming a fixed one-pass-per-step order, so branching and looping runs display accurately rather than being silently mis-rendered.
- **FR-016**: A workflow step that was defined but not executed on a given run's actual path (because a different branch was taken) MUST be shown in that run's view visually distinguished as "not taken this run" — distinct from pending, running, completed, or failed — rather than omitted entirely or shown as if awaiting execution.
- **FR-017**: While a run is in progress, the live progress indicator MUST NOT display a fixed "step N of total" count for a workflow where any step has a non-empty `branches` list, since the total number of steps on the eventual path isn't known until the run resolves; it MUST instead show a running count of steps executed so far with no denominator. Workflows with no step's `branches` populated MUST continue to show the existing fixed "N / total" indicator unchanged, even if a step uses `default_next` to jump backward — that case is treated as a reordering override, not branching, for this requirement's purposes.

### Key Entities

- **Workflow Step**: A single unit of work within a workflow. Gains a stable identifier and an optional set of branches plus an optional default-next override, in addition to its existing task description and success-verification criteria.
- **Branch**: A condition (natural-language description of a step outcome) paired with a target — either another step in the same workflow, or a terminal "end" / "fail" outcome. Belongs to exactly one step and is evaluated only after that step succeeds.
- **Workflow Run (Execution)**: A single execution of a workflow. Gains a record of which step was actually visited at each point (including loop revisits and which branch was taken), used both for the loop-limit safeguard and for after-the-fact explanation of the path taken.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A workflow containing a conditional (branching) step correctly follows the matching path in 100% of test runs where the step's output unambiguously matches one defined branch condition.
- **SC-002**: Every workflow that existed before this feature shipped continues to produce identical run results (same steps, same order, same pass/fail outcome) after the feature ships, with zero required user action.
- **SC-003**: A workflow with a looping branch that never resolves is stopped automatically within a bounded number of step revisits (default 3) in 100% of cases, never running indefinitely.
- **SC-004**: A user reviewing a completed run of a branching workflow can identify which path was taken and why, without needing to inspect anything beyond the run's own record.
- **SC-005**: The planner's prompt and parsing logic correctly produce a branching workflow for a description containing explicit conditional language, and a plain linear workflow otherwise, verified by unit tests against representative fixed inputs. Real-model classification accuracy across a broader input distribution is not measured by this spec — see Assumptions.
- **SC-006**: The existing Workflows screen shows a completely accurate run history (correct steps, correct order, correct repeat count for loops) for 100% of branching and looping workflow runs, with zero visual regression for existing non-branching workflows.

## Assumptions

- Branch condition matching is based on interpreting the step's natural-language output against the natural-language branch conditions — it is not a strict programmatic expression language (no boolean operators, variable references, or comparisons against structured data). This matches how step verification already works today.
- Only one step is "active" at a time; this feature does not introduce concurrent/parallel step execution or multi-path fan-out. A branch always selects exactly one next step (or terminal outcome).
- The default loop-revisit limit (3) is a system-wide default rather than something workflow authors configure per-workflow in this iteration.
- This spec covers the data model, execution behavior, and planning/authoring behavior needed for branching to work end-to-end, plus keeping the already-existing Workflows screen accurate for branching/looping runs (User Story 5). It does not cover building any new graph/branch editor or graphical branch-authoring UI — that visual representation of branch structure was out of scope here and is specified separately in [104-workflow-flowchart-view](../104-workflow-flowchart-view/spec.md), which replaces the linear run view built by this spec with a flowchart rendering of the same `branches`/`default_next`/`branch_taken` data. The distinction: fixing the existing linear run view so it doesn't mis-render was in scope for this spec; the new visual representation of branch structure is scoped to 104.
- Existing workflow storage can accommodate the new optional step fields (identifier, branches, default-next) without requiring a breaking change to how workflows are saved; this is treated as an additive change.
- `default_next` alone (with an empty `branches` list) is treated as a plain reordering override, not "branching" — it does not trigger FR-017's progress-indicator change, even if it points backward and is caught by the FR-008 loop guard.
- SC-005 is validated only by unit tests against fixed, representative inputs (see FR-012's tests); no empirical measurement against real-model output across a broader input distribution is performed as part of this feature.
