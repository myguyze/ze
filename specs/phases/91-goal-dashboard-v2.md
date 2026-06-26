# Phase 91 — Goal Dashboard v2

**Status:** Pending
**Depends on:** Phase 19 (Goal Engine), Phase 23 (Goal Engine v2), Phase 45 (Native App Interface), Phase 72 (API Client Codegen)
**Packages touched:** `apps/ze-api`, `apps/ze-web`

---

## What this is

An expanded goals view that gives the user full visibility into what Ze is autonomously
working toward. The current goals page (`/goals`) shows only a flat list of goal names
and statuses. This phase adds:

- **Milestone timeline** — ordered list of milestones per goal with status badges
- **Verification gate status** — when Ze is paused awaiting approval
- **Execution trace log** — tool calls and outputs from the GoalAgent's agentic loop
- **Learnings sidebar** — extracted learnings from completed milestones

The result is a dashboard where the user can see every milestone Ze has completed,
what it did, and what it learned — without reading raw logs.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| API shape | New `GET /api/v0/goals/{goal_id}` detail endpoint | Existing `listGoals` returns flat list only; detail is loaded on demand |
| Milestone + gate data | Joined from `goal_milestones` + `goal_gates` in one query | One round-trip per goal open |
| Execution traces | `GET /api/v0/goals/{goal_id}/traces` separate endpoint | Traces can be voluminous; lazy-loaded when user expands a milestone |
| UI layout | Vertical timeline per goal, full-page detail view | Timeline is clearer than kanban for ordered milestones |
| Goal list | Keep existing `/goals` as entry point; click → detail view | Consistent with existing web routing pattern |
| Learnings | Rendered as simple bullet list from `GoalLearning` rows | No special UI required for v1 |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `GET /api/v0/goals/{goal_id}` detail endpoint | 🔲 Pending |
| `GET /api/v0/goals/{goal_id}/traces` endpoint | 🔲 Pending |
| Schema types (`GoalDetailResponse`, etc.) | 🔲 Pending |
| Codegen update | 🔲 Pending |
| `pages/goal-detail/` FSD slice | 🔲 Pending |
| `MilestoneTimeline` component | 🔲 Pending |
| `GateStatusCard` component | 🔲 Pending |
| `ExecutionTraceLog` component | 🔲 Pending |
| `GoalLearningsList` component | 🔲 Pending |

---

## REST API (`apps/ze-api`)

### `GET /api/v0/goals/{goal_id}`

Full goal detail including milestones and gates.

```python
class MilestoneResponse(BaseModel):
    id: UUIDType
    title: str
    description: str
    sequence: int
    status: str                # MilestoneStatus value
    output: str | None         # populated after completion
    reuse_hint: str | None
    completed_at: datetime | None
    created_at: datetime

class GateResponse(BaseModel):
    id: UUIDType
    after_sequence: int
    title: str
    status: str                # GateStatus value
    context_summary: str | None
    plan_summary: str | None
    user_feedback: str | None
    fired_at: datetime | None
    resolved_at: datetime | None

class LearningResponse(BaseModel):
    id: UUIDType
    content: str
    source: str
    created_at: datetime

class GoalDetailResponse(BaseModel):
    id: UUIDType
    title: str
    objective: str
    success_condition: str
    status: str
    type: str
    time_horizon: str | None
    learnings_summary: str | None   # goal.learnings free-text
    retrospective_text: str | None
    created_at: datetime
    updated_at: datetime
    milestones: list[MilestoneResponse]
    gates: list[GateResponse]
    learnings: list[LearningResponse]
```

- **operation_id:** `getGoalDetail`
- **404** when goal not found.

### `GET /api/v0/goals/{goal_id}/traces`

Execution traces for all milestones of a goal, ordered by `seq` ASC within each milestone.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `milestone_id` | UUID | — | Filter to a single milestone |
| `limit` | int | 100 | Max rows |
| `offset` | int | 0 | Pagination offset |

```python
class ExecutionTraceResponse(BaseModel):
    id: UUIDType
    milestone_id: UUIDType
    goal_id: UUIDType
    seq: int
    tool_name: str
    args: dict
    result: str
    duration_ms: int
    success: bool
    error: str | None
    created_at: datetime
```

- **operation_id:** `listGoalTraces`

---

## GoalStore extension

Add to `PostgresGoalStore` (and update the `GoalStore` Protocol):

```python
async def get_goal_detail(self, goal_id: UUID) -> GoalDetail | None:
    """Returns goal + milestones + gates + learnings in one query."""

async def list_traces(
    self,
    goal_id: UUID,
    milestone_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ExecutionTrace]: ...
```

`GoalDetail` is a new dataclass in `ze_automation/goals/types.py`:

```python
@dataclass
class GoalDetail:
    goal: Goal
    milestones: list[Milestone]
    gates: list[VerificationGate]
    learnings: list[GoalLearning]
```

---

## Frontend (`apps/ze-web`)

### Route

`/goals/:goalId` — detail page. Clicking a goal row in the existing `/goals` list
navigates here.

### FSD layout

```
pages/goal-detail/
  ui/
    GoalDetailPage.tsx       # layout shell, header, sidebar
widgets/milestone-timeline/
  ui/
    MilestoneTimeline.tsx    # ordered list of milestones
    MilestoneRow.tsx         # status icon + title + output snippet + expand
    ExecutionTraceLog.tsx    # lazy-loaded trace table for a milestone
    TraceRow.tsx             # tool_name, result snippet, duration, ✓/✗
widgets/gate-status/
  ui/
    GateStatusCard.tsx       # shows gate title, status, context_summary, feedback
widgets/goal-learnings/
  ui/
    GoalLearningsList.tsx    # bullet list of GoalLearning items
```

### Layout

```
┌─────────────────────────────────────────────────────┐
│  ← Goals   "Learn Spanish" · active                 │
│  "Achieve conversational fluency in 3 months"       │
├────────────────────────────────┬────────────────────┤
│  Milestone Timeline            │  Learnings         │
│                                │  • Users respond   │
│  ✅ 1. Find learning resources │    better to…      │
│     Output: "Found 3 courses…" │  • Duolingo streak │
│     [Show 4 tool calls ▾]      │    works for…      │
│                                │                    │
│  ✅ 2. Create study schedule   ├────────────────────┤
│     Output: "Schedule added…"  │  Gate              │
│     [Show 2 tool calls ▾]      │  "Is the schedule  │
│                                │   working?" ⏳     │
│  ⏳ 3. Week 1 practice         │  Awaiting approval │
│     (in progress)              │                    │
│                                │                    │
│  🔲 4. Pronunciation review    │                    │
└────────────────────────────────┴────────────────────┘
```

### Milestone expand

Clicking "Show N tool calls ▾" fires `listGoalTraces` with `milestone_id` and renders
`ExecutionTraceLog` inline below the milestone row (same lazy-load pattern as Phase 89).

### Gate card

When a gate has `status = "awaiting_approval"`, show a CTA button "Approve & continue"
that calls `POST /api/v0/goals/{goal_id}/start` (reusing existing endpoint). Gate cards
with other statuses are read-only.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `PostgresGoalStore` | `get_goal_detail`, `list_traces` |
| `goal_execution_traces` table (zc006) | Source of execution traces |
| `goal_milestones`, `goal_gates`, `goal_learnings` tables | Milestone and gate data |
| `GET /api/v0/goals/{id}`, `GET /api/v0/goals/{id}/traces` | New API endpoints |
| Existing `POST /api/v0/goals/{id}/start` | Gate approval from dashboard |

---

## Out of scope

- Editing goals or milestones from the UI.
- Creating new goals from this page (done via chat).
- Real-time milestone progress streaming (polling on page focus is sufficient).
- Goal suggestions panel (Phase 25 feature; consider linking from this page in a later phase).

---

## Testing

| Area | Tests |
|------|-------|
| `get_goal_detail` | Returns all relations; 404 for unknown id |
| `list_traces` | Filtered by milestone_id; paginated |
| `GET /api/v0/goals/{id}` | Full response shape validation |
| `MilestoneTimeline` | Renders all statuses; expand fires trace fetch |
| `GateStatusCard` | Shows approve CTA only for awaiting_approval |
