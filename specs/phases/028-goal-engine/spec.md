# Spec 28 — Goal Engine

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze/goals/` module — types, store, planner, executor | ✅ Done |
| Migration 016 — `goals`, `goal_milestones`, `goal_gates`, `goal_learnings` | ✅ Done |
| `GoalPlanner` — LLM-driven decomposition into milestones + gates | ✅ Done |
| `GoalExecutor` — autonomous loop: advance milestones, fire gates | ✅ Done |
| `GoalAgent` — create, inspect, pause, abandon goals via conversation | ✅ Done |
| Telegram gate flow — rich approval message + inline keyboard + redirect | ✅ Done |
| Proactive milestone progress updates | ✅ Done |
| Scheduler wiring — periodic `advance` calls | ✅ Done |
| Container wiring | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze currently has two execution primitives: fully autonomous (WorkflowAgent runs
to completion) and per-action confirmation (the capability gate pauses for every
write). Neither is right for multi-week goals — you want Ze to batch meaningful
work and check in at the right moments, not constantly interrupt.

The Goal Engine introduces three new primitives:

- **Goal** — a stated objective with a success condition and time horizon. Ze
  decomposes it into milestones and executes them autonomously.
- **VerificationGate** — a pause point where Ze surfaces what it has done, what
  it plans to do next, and waits for explicit approval before continuing.
- **Learning** — an insight Ze captures at each milestone boundary and synthesises
  into its understanding of the goal over time.

Together these give Ze the ability to work on multi-week tasks — running a
prospecting campaign, preparing for a conference, executing a research agenda —
while keeping the user in control at meaningful decision points.

---

## Relationship to Existing Systems

| System | Role | Relationship |
|--------|------|--------------|
| `WorkflowAgent` | Executes a fixed ordered list of tasks in one run | Goals call it to execute milestone tasks |
| `WorkflowScheduler` | Runs periodic/cron jobs | Drives the goal `advance` loop |
| `ProspectingAgent` | Autonomous research loop | Becomes a milestone executor in Phase 20 |
| `prospect_campaigns` | Tracks a prospecting run | Becomes a Goal of type `outreach` in Phase 20 |
| Telegram confirmation flow | Per-action approve/reject | Gates are the multi-step equivalent |

Goals sit *above* workflows: a goal spans weeks, gates span days, milestones span
hours. A workflow execution is what happens inside a single milestone.

---

## Out of Scope

- Prospecting as a Goal (Phase 20 — uses this engine).
- Goal templates or library of predefined goal types.
- Multi-user goals or collaborative goals.
- Goal dependencies (one goal unblocking another).
- Automated success detection — Ze flags a goal complete, but the user confirms.

---

## Repository Layout

```
ze/
├── ze/
│   ├── goals/
│   │   ├── __init__.py
│   │   ├── types.py         # Goal, Milestone, VerificationGate, GoalLearning
│   │   ├── store.py         # GoalStore
│   │   ├── planner.py       # GoalPlanner — LLM decomposition
│   │   └── executor.py      # GoalExecutor — advance loop
│   └── agents/
│       └── goals/
│           ├── __init__.py
│           └── agent.py     # GoalAgent
└── migrations/versions/
    └── 016_goals.py
```

---

## Types (`ze/goals/types.py`)

```python
class GoalStatus(StrEnum):
    PLANNING          = "planning"           # just created, plan not yet approved
    ACTIVE            = "active"             # executing milestones
    AWAITING_GATE     = "awaiting_gate"      # paused at a verification gate
    PAUSED            = "paused"             # user-paused
    COMPLETED         = "completed"
    ABANDONED         = "abandoned"

class MilestoneStatus(StrEnum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    SKIPPED    = "skipped"

class GateStatus(StrEnum):
    PENDING            = "pending"           # not yet reached
    AWAITING_APPROVAL  = "awaiting_approval" # Telegram message sent, waiting
    APPROVED           = "approved"
    STOPPED            = "stopped"           # user stopped the goal at this gate
    REDIRECTED         = "redirected"        # user sent new instructions

@dataclass
class Goal:
    title: str
    objective: str           # what the user wants to achieve (free text)
    success_condition: str   # what "done" looks like
    status: GoalStatus = GoalStatus.PLANNING
    type: str = "custom"     # "outreach" | "research" | "custom"
    time_horizon: str = ""   # "6 weeks", "by end of May", etc.
    learnings: str = ""      # synthesised learning text, updated at each gate
    id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

@dataclass
class Milestone:
    goal_id: UUID
    title: str
    description: str         # task instruction passed to the agent
    sequence: int            # 1-based ordering
    agent_hint: str | None = None   # which agent should execute this
    intent: str = "execute"
    status: MilestoneStatus = MilestoneStatus.PENDING
    output: str = ""         # stored when completed
    id: UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None

@dataclass
class VerificationGate:
    goal_id: UUID
    after_sequence: int      # fires after the milestone with this sequence completes
    title: str
    status: GateStatus = GateStatus.PENDING
    context_summary: str = ""   # filled in when fired: what Ze has done
    plan_summary: str = ""      # filled in when fired: what Ze plans next
    user_feedback: str = ""     # filled in if redirected
    id: UUID | None = None
    fired_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None

@dataclass
class GoalLearning:
    goal_id: UUID
    content: str
    source: str              # "milestone_completion" | "gate_feedback" | "user_message"
    id: UUID | None = None
    created_at: datetime | None = None
```

---

## Migration 016 (`migrations/versions/016_goals.py`)

```sql
CREATE TABLE goals (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title             TEXT        NOT NULL,
    objective         TEXT        NOT NULL,
    success_condition TEXT        NOT NULL,
    time_horizon      TEXT        NOT NULL DEFAULT '',
    status            TEXT        NOT NULL DEFAULT 'planning',
    type              TEXT        NOT NULL DEFAULT 'custom',
    learnings         TEXT        NOT NULL DEFAULT '',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX goals_status_idx ON goals(status, created_at DESC);

CREATE TABLE goal_milestones (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id      UUID        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    title        TEXT        NOT NULL,
    description  TEXT        NOT NULL,
    sequence     INT         NOT NULL,
    agent_hint   TEXT,
    intent       TEXT        NOT NULL DEFAULT 'execute',
    status       TEXT        NOT NULL DEFAULT 'pending',
    output       TEXT        NOT NULL DEFAULT '',
    completed_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(goal_id, sequence)
);
CREATE INDEX goal_milestones_goal_id_idx ON goal_milestones(goal_id, sequence);

CREATE TABLE goal_gates (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id          UUID        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    after_sequence   INT         NOT NULL,
    title            TEXT        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'pending',
    context_summary  TEXT        NOT NULL DEFAULT '',
    plan_summary     TEXT        NOT NULL DEFAULT '',
    user_feedback    TEXT        NOT NULL DEFAULT '',
    fired_at         TIMESTAMPTZ,
    resolved_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(goal_id, after_sequence)
);
CREATE INDEX goal_gates_goal_id_idx ON goal_gates(goal_id, after_sequence);

CREATE TABLE goal_learnings (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id    UUID        NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    content    TEXT        NOT NULL,
    source     TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX goal_learnings_goal_id_idx ON goal_learnings(goal_id, created_at DESC);
```

---

## `GoalStore` (`ze/goals/store.py`)

```python
class GoalStore:
    async def create_goal(self, goal: Goal) -> Goal: ...
    async def get_goal(self, goal_id: UUID) -> Goal | None: ...
    async def list_active(self) -> list[Goal]: ...             # status in (active, awaiting_gate)
    async def update_status(self, goal_id: UUID, status: GoalStatus) -> None: ...
    async def append_learnings(self, goal_id: UUID, text: str) -> None: ...

    async def create_milestone(self, m: Milestone) -> Milestone: ...
    async def list_milestones(self, goal_id: UUID) -> list[Milestone]: ...
    async def update_milestone(self, milestone_id: UUID, status: MilestoneStatus, output: str = "") -> None: ...

    async def create_gate(self, gate: VerificationGate) -> VerificationGate: ...
    async def get_pending_gate(self, goal_id: UUID) -> VerificationGate | None: ...
    async def fire_gate(self, gate_id: UUID, context_summary: str, plan_summary: str) -> None: ...
    async def resolve_gate(self, gate_id: UUID, status: GateStatus, user_feedback: str = "") -> None: ...

    async def add_learning(self, learning: GoalLearning) -> None: ...
    async def list_learnings(self, goal_id: UUID) -> list[GoalLearning]: ...
```

---

## `GoalPlanner` (`ze/goals/planner.py`)

Takes a `Goal` and produces a list of `Milestone` objects and `VerificationGate`
placements. Uses an LLM call modelled on `WorkflowPlanner`.

### System prompt contract

Input: `objective`, `success_condition`, `time_horizon`

Output: JSON with two keys:
```json
{
  "milestones": [
    {
      "title": "Find 20 charter operators in Portugal",
      "description": "Use the research and browser agents to find ...",
      "agent_hint": "prospecting",
      "intent": "execute",
      "sequence": 1
    }
  ],
  "gates": [
    {
      "after_sequence": 2,
      "title": "Review target list before outreach"
    }
  ]
}
```

Gate placement guidelines baked into the prompt:
- Always gate before the first outreach action.
- Gate after any milestone that produces irreversible output (sent emails, external posts).
- Gate at natural progress checkpoints (~every 3 milestones for long goals).
- At minimum one gate, even for short goals.

### `plan(goal: Goal) -> tuple[list[Milestone], list[VerificationGate]]`

Returns unsaved dataclass instances. `GoalExecutor` saves them after the initial
plan is approved.

---

## `GoalExecutor` (`ze/goals/executor.py`)

The core autonomous loop. All execution is driven through `advance(goal_id)`,
which is called by the scheduler and by the gate-approval handler.

```python
class GoalExecutor:
    async def advance(self, goal_id: UUID) -> None: ...
    async def handle_gate_approved(self, gate_id: UUID) -> None: ...
    async def handle_gate_stopped(self, gate_id: UUID) -> None: ...
    async def handle_gate_redirected(self, gate_id: UUID, feedback: str) -> None: ...
```

### `advance(goal_id)` logic

```
1. Load goal. If not ACTIVE → return.
2. Find next pending milestone by sequence.
3. If no pending milestone → mark goal COMPLETED, notify, return.
4. Check if there is a gate for (current_sequence - 1) that is still PENDING.
   If yes → fire the gate (fill context + plan, send Telegram, set AWAITING_GATE) → return.
5. Mark milestone IN_PROGRESS.
6. Execute the milestone task via the appropriate agent.
7. Store the milestone output. Mark COMPLETED.
8. Extract a learning from the output (LLM call), store in goal_learnings.
9. Send a brief progress notification: "✅ [milestone title] done (N/total)."
10. Loop back to step 2.
```

### Gate firing

When `advance` reaches a gate:
1. Compile `context_summary` — list of completed milestones with their outputs (summarised).
2. Compile `plan_summary` — list of remaining milestones up to the next gate.
3. Call `GoalStore.fire_gate(gate_id, context_summary, plan_summary)`.
4. Set goal status to `AWAITING_GATE`.
5. Send the Telegram gate message (see below).
6. Return — execution pauses until the user responds.

### Gate approval flow

- **Approved** → `handle_gate_approved`: mark gate APPROVED, set goal ACTIVE, call `advance`.
- **Stopped** → `handle_gate_stopped`: mark gate STOPPED, set goal ABANDONED, notify.
- **Redirected** → `handle_gate_redirected`: store `user_feedback` on the gate, re-plan
  remaining milestones incorporating the feedback (LLM call), replace pending milestones
  in the DB, mark gate REDIRECTED, set goal ACTIVE, call `advance`.

### Milestone execution

The executor builds an `AgentContext` from the milestone `description` + `intent`
and dispatches it through the existing agent registry, exactly like the workflow
executor does today. The `agent_hint` selects the agent.

---

## Telegram Gate Flow

### Gate message format

```
🎯 *[goal title]* — checkpoint

*What Ze has done:*
[context_summary — bullet list of completed milestones with brief outputs]

*What Ze plans next:*
[plan_summary — bullet list of upcoming milestones until the next gate]

Approve to continue, or send new instructions.
```

Inline keyboard:

```
[✅ Proceed]  [🛑 Stop]  [✏️ Redirect]
```

Callback data:
- `goal:approve:<gate_id>` → approve
- `goal:stop:<gate_id>` → stop/abandon
- `goal:redirect:<gate_id>` → triggers ForceReply for free-text instructions

### Handling responses

Add a `goal:` branch to `ZeBot.handle_callback`. The gate_id is a UUID (≤36
chars); callback payloads stay under 64 bytes since the gate_id is the only
variable-length part.

The Redirect flow mirrors the existing ForceReply pattern in `handle_callback`:
set state to awaiting redirect, then on next user message call
`GoalExecutor.handle_gate_redirected(gate_id, text)`.

---

## `GoalAgent` (`ze/agents/goals/agent.py`)

Handles user-facing goal management via conversation. Intents: `create`, `read`,
`update` (pause/resume), `delete` (abandon).

**Tools:**

- `create_goal(title, objective, success_condition, time_horizon)` — WRITE.
  Creates a goal, runs the planner, sends a plan-confirmation message (same
  `plan_confirmation_keyboard` pattern used by WorkflowAgent), waits for approval.
  On approval: saves milestones + gates, sets status to ACTIVE, schedules first
  `advance` call.

- `get_goal_status(goal_id)` — READ. Returns current status, completed/pending
  milestone count, pending gate if any, and latest learnings summary.

- `list_goals` — READ. Returns all active/awaiting-gate goals with one-line
  summaries.

- `pause_goal(goal_id)` / `resume_goal(goal_id)` — WRITE.

- `abandon_goal(goal_id)` — WRITE.

The GoalAgent does not execute milestones — that is `GoalExecutor`'s job.

---

## Scheduler Wiring

A periodic `advance` sweep runs every 15 minutes for all ACTIVE goals:

```python
async def _sweep_active_goals():
    goals = await goal_store.list_active()
    for goal in goals:
        await goal_executor.advance(goal.id)

workflow_scheduler.schedule_job(
    fn=_sweep_active_goals,
    cron="*/15 * * * *",
    job_id="goal_advance_sweep",
)
```

The sweep is lightweight — it exits early for goals with no actionable next step.
For long-running milestone tasks, `advance` fires `asyncio.create_task` to avoid
blocking the scheduler thread.

---

## Container Wiring

```python
goal_store     = GoalStore(pool=pool)
goal_planner   = GoalPlanner(openrouter_client=openrouter_client, settings=settings)
goal_executor  = GoalExecutor(
    goal_store=goal_store,
    goal_planner=goal_planner,
    notifier=notifier,
    settings=settings,
)
```

`GoalExecutor` is passed to `bootstrap_agents` so `GoalAgent` can resolve it.
`goal_store` and `goal_executor` are added to `ZeBot` and to `_make_config` so
the Telegram gate handler can call `handle_gate_approved` etc.

---

## Error Handling

New errors in `ze/errors.py`:

```python
class GoalError(ZeError): ...
class GoalPlanError(GoalError): ...        # planner returned invalid output
class GoalExecutionError(GoalError): ...   # milestone execution failed
```

A failed milestone does not stop the goal. `advance` marks it SKIPPED, stores
the error as its output, adds a learning ("milestone X failed: [reason]"), and
continues to the next milestone. The user is notified via a brief Telegram
message so they can redirect if needed.

---

## Testing

- `tests/goals/test_store.py` — mock asyncpg pool; test all GoalStore methods,
  gate firing/resolution state transitions.
- `tests/goals/test_planner.py` — mock OpenRouter; test JSON parsing, milestone
  ordering, gate placement validation.
- `tests/goals/test_executor.py` — mock GoalStore + agents; test the `advance`
  loop (normal flow, gate pause, milestone failure skip, completion).
- `tests/goals/test_gate_flow.py` — test approve/stop/redirect paths including
  the replanning step on redirect.
- `tests/agents/goals/test_goal_agent.py` — mock GoalStore + GoalPlanner; test
  create/status/list/abandon tool calls.

---

## What This Enables

After this phase:

- Ze can execute any multi-week objective autonomously, pausing at meaningful
  checkpoints for human approval.
- The verification gate is a first-class primitive — not hardcoded to prospecting
  or any other domain.
- Phase 20 (prospecting loop) uses this engine: a campaign becomes a Goal of type
  `outreach`, milestones map to find/draft/send/follow-up steps, and the "show me
  what you'll send" confirmation is the gate before the send milestone.
- Future goal types (conference prep, research agenda, hiring pipeline) require
  only a new goal type string and domain-appropriate milestone descriptions — no
  new infrastructure.
