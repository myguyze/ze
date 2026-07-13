# Feature Specification: Workflow Flowchart View

**Feature Branch**: `104-workflow-flowchart-view`

**Created**: 2026-07-12

**Status**: Implemented

**Input**: User description: "Improve the UI/UX of the workflows screen. Workflows form a flow with branching sometimes — the current Workflows screen renders a run as a flat vertical timeline that replays execution order and dumps every skipped step in a greyed-out list at the end (built by [102-workflow-branching](../102-workflow-branching/spec.md)), without ever showing the workflow's actual branch structure. Replace it with a real flowchart: steps as nodes, `branches`/`default_next` as labeled directed edges, with the actually-executed path (from `step_results[].branch_taken`) highlighted against the full graph shape. Full replacement of the timeline view, not a toggle between the two. Top-to-bottom orientation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See a workflow's actual shape, not just its history (Priority: P1)

A user opens a branching workflow's detail page and sees the full graph of possible steps and branches — not just a flat replay of what happened on the last run. They can immediately tell which steps are alternatives to each other and what condition routes to which.

**Why this priority**: This is the core value of the rework — understanding structure, not just chronology. The prior timeline view could not represent this at all.

**Independent Test**: Open the detail page for a workflow with a branching step; confirm both branch targets render as nodes connected from the same source step, each edge labeled with its condition text.

**Acceptance Scenarios**:

1. **Given** a workflow step with two branches, **When** its detail page renders, **Then** both branch target steps appear as nodes with edges from the source step labeled with each branch's condition.
2. **Given** a step with a `default_next` override and no branches, **When** the graph renders, **Then** a single unlabeled edge connects it to its `default_next` target.

---

### User Story 2 - See which path a run actually took (Priority: P1)

A user viewing a specific run (live or historical) can see, overlaid on the full graph, exactly which nodes executed and which edge was followed at each branch point — distinct from steps that exist in the workflow but weren't part of this run.

**Why this priority**: Matches the correctness guarantee [102-workflow-branching](../102-workflow-branching/spec.md) established for the timeline view (FR-015/FR-016) — the graph view must not regress that guarantee, only present it differently.

**Independent Test**: Run a branching workflow where one of two branches fires; open that run; confirm the taken edge and its downstream nodes are visually distinct (highlighted) from the untaken branch's nodes and edge.

**Acceptance Scenarios**:

1. **Given** a completed run where branch condition "ok" fired at a step, **When** viewing that run, **Then** the edge labeled "ok" and the nodes it leads to are shown taken/highlighted, and the sibling branch's nodes are shown as not-taken.
2. **Given** a run currently in progress, **When** viewing it, **Then** the node for the step currently executing is shown in a running state, determined by following the last completed step's branch/default edge — not by assuming a fixed next-index.
3. **Given** a failed run whose last known step succeeded, **When** viewing it, **Then** the step that would have executed next (per the graph) is shown in a failed state.
4. **Given** a looped step that executed more than once in a run, **When** viewing that run, **Then** the node reflects the most recent execution's outcome and output.
5. **Given** a non-branching (linear) workflow, **When** viewing any of its runs, **Then** every step renders as a straight top-to-bottom chain with no behavioral regression from the prior linear rendering.

---

### User Story 3 - Inspect a step's detail without leaving the graph (Priority: P2)

A user clicks a node to see its task text, agent hint, verify criteria, and (if the run touched it) output/error/duration, without navigating away from the graph.

**Why this priority**: The prior timeline view supported an inline expand-in-place for this; the graph needs an equivalent so no information is lost in the rework.

**Independent Test**: Click a node with output; confirm a detail panel opens showing that step's markdown-rendered output.

**Acceptance Scenarios**:

1. **Given** a node with a completed result, **When** clicked, **Then** a side panel shows its output (rendered as markdown) and duration.
2. **Given** the same node, **When** clicked again (or the panel's close control is used), **Then** the panel closes and no node remains selected.

### Edge Cases

- A workflow with no steps: the graph area shows the same "No steps defined." message the prior list view showed.
- A step whose branch or default target id doesn't resolve to another authored step (data integrity issue upstream): the edge is simply not drawn; this spec does not add new validation beyond what [102-workflow-branching](../102-workflow-branching/spec.md) FR-010 already guarantees at save time.
- A very large/wide graph: the canvas supports pan and zoom (via the underlying flow-rendering library) rather than requiring the whole graph to fit the panel at once; a "fit view" toolbar action re-centers it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workflow detail screen MUST render a workflow's steps and branch structure as a node/edge flowchart rather than a flat timeline, laid out top-to-bottom.
- **FR-002**: The graph MUST include one node per authored step and one edge per authored `branches[]` entry (labeled with the branch condition) plus one edge for `default_next` when present, regardless of whether a given run executed them.
- **FR-003**: When a run (live or historical) is being viewed, each node MUST reflect that step's status for that run: completed-success, completed-failure, currently running, inferred-failed (the step that would run next after a run failed without its own result), not-taken, or idle/pending (no run selected).
- **FR-004**: When a run is being viewed, each edge MUST be marked "taken" if it was actually followed during that run, determined by matching `step_results[].branch_taken` (or, when null, the step's `default_next`) against the edge's source step and condition — not by execution order alone.
- **FR-005**: A step that executed more than once within a run (a loop) MUST be represented by a single node reflecting its most recent execution's status and output; the loop-back edge MUST be marked taken.
- **FR-006**: Clicking a node MUST open a detail panel showing that step's task, agent hint, verify criteria, and (if it has a result for the viewed run) output, error, and duration; clicking again or using the panel's close control MUST close it.
- **FR-007**: The view MUST provide a "fit view" control to re-center/zoom the graph, and a control to hide/show not-taken steps.
- **FR-008**: This view MUST fully replace the prior timeline list view (`WorkflowStepsList`) — there is no list/flow toggle.
- **FR-009**: A workflow with no branching steps MUST render as a single top-to-bottom chain with no visual regression in the information conveyed versus the prior linear timeline.

### Key Entities

- **Workflow Graph Node**: One per authored `WorkflowStepResponse`, carrying the step definition plus a derived run-relative status.
- **Workflow Graph Edge**: One per authored branch or default-next relationship, carrying an optional condition label and a derived run-relative "taken" flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For any workflow with at least one branching step, a user can identify every possible path through the workflow (not just the one most recently run) from the detail page alone.
- **SC-002**: For any completed or in-progress run, the taken path is visually distinguishable from untaken branches without needing to read raw execution data.
- **SC-003**: Existing linear (non-branching) workflows show zero loss of information versus the prior timeline view (all steps, statuses, and outputs remain inspectable).

## Assumptions

- This spec supersedes the "future, separate effort" note in [102-workflow-branching](../102-workflow-branching/spec.md)'s Assumptions section — that spec's FR-015/FR-016/FR-017 requirements on the *prior* timeline view are retired along with the view itself; this spec's FR-003/FR-004 are their graph-view equivalents.
- No new graph/branch *authoring* or editing UI is introduced — this is a read-only visualization of the existing `branches`/`default_next` data, same scope boundary [102-workflow-branching](../102-workflow-branching/spec.md) drew for its own out-of-scope note.
- Node layout is computed automatically (top-to-bottom, via graph layout, not manually positioned or user-draggable); manual node repositioning is not part of this spec.
- Parallel/concurrent step execution remains out of scope, per [102-workflow-branching](../102-workflow-branching/spec.md)'s existing assumption — the graph always shows exactly one active node per in-progress run.
