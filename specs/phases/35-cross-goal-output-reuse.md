# Cross-Goal Output Reuse — Spec

> **Package:** `ze_personal` (types, store, planner, executor, tools)
> **Phase:** 27
> **Status:** Pending
> **Depends on:** Phase 26 ([34-stuck-goal-detection.md](34-stuck-goal-detection.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `PriorMilestoneOutput` type | 🔲 Pending |
| `reuse_hint` field on `Milestone` | 🔲 Pending |
| `GoalStore.list_completed_milestone_summaries()` | 🔲 Pending |
| `GoalPlanner.plan()` cross-goal context injection | 🔲 Pending |
| `GoalPlanner.replan_remaining()` cross-goal context injection | 🔲 Pending |
| `_build_milestone_prompt` prior work section | 🔲 Pending |
| `create_goal` tool queries and passes prior work | 🔲 Pending |
| Executor replan paths query and pass prior work | 🔲 Pending |
| Migration: `reuse_hint` column | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

Ze plans each goal in isolation. When a new goal overlaps in research or domain with a recently completed goal, Ze re-does work it has already done — re-scraping the same companies, re-surveying the same market, re-drafting the same type of document. The outputs from prior goals exist in `goal_execution_traces` and `goal_milestones.output`, but the planner has no visibility into them at planning time.

This phase gives `GoalPlanner.plan()` a window into recent completed milestone outputs across all goals. When the planner identifies genuine overlap, it embeds a reuse hint in the affected milestone's instructions. The agent executing that milestone sees the hint and can retrieve the prior trace before deciding whether to re-run the work.

The reuse decision is always advisory — the agent decides at execution time whether the prior output is fresh and relevant enough to reuse. Ze never silently skips work.

---

## Responsibilities

- Query recently completed milestone outputs (across goals, time-bounded) before planning a new goal.
- Pass those summaries to the planner as optional context.
- Let the planner LLM identify which planned milestones have genuine prior work overlap, and embed a `reuse_hint` in those milestones' instructions.
- Surface the hint to the executing agent via `_build_milestone_prompt` so it can call `get_milestone_trace` before re-running.
- Apply the same cross-goal context to replanning paths (redirect, adaptive replan, steer).

---

## Out of Scope

- **Cross-goal learning promotion** — extracting generalizable insights from goal learnings and promoting them to user facts. Deferred as a separate phase.
- **Conflict or synergy detection** — flagging that two goals are working at cross purposes. Ruled out as low signal-to-noise for a single user with 3–4 concurrent goals.
- **Automatic skipping** — Ze deciding on its own to skip a milestone because prior work exists. Reuse is always surfaced to the agent as a hint; the final decision is the agent's.
- **Semantic similarity retrieval** — embedding milestone outputs and running vector search. A time-windowed DB query with LLM synthesis is sufficient for this scope.
- **Cross-goal context in execution traces** — trace records do not change; this phase only adds planning-time context.

---

## Module Location

```
packages/ze-personal/
  ze_personal/
    goals/
      types.py          ← add PriorMilestoneOutput; add reuse_hint field to Milestone
      store.py          ← add list_completed_milestone_summaries() to GoalStore protocol
      postgres.py       ← implement list_completed_milestone_summaries()
      planner.py        ← plan() and replan_remaining() gain optional prior_work param
      executor.py       ← _build_milestone_prompt adds [PRIOR WORK] section;
                          replan call sites pass prior work
    agents/goals/
      tools.py          ← create_goal queries prior work before calling planner.plan()

packages/ze/
  ze/
    migrations/
      0NN_milestone_reuse_hint.sql  ← ALTER TABLE goal_milestones ADD COLUMN reuse_hint
```

---

## Feature 1: Data Types

### `PriorMilestoneOutput`

```python
# ze_personal/goals/types.py

@dataclass
class PriorMilestoneOutput:
    goal_id: UUID
    goal_title: str
    milestone_id: UUID
    milestone_title: str
    output_snippet: str      # first 200 chars of milestone output
    completed_days_ago: int
```

### `Milestone` — new field

Add one field to the existing `Milestone` dataclass:

```python
@dataclass
class Milestone:
    ...
    reuse_hint: str = ""   # set by planner when prior work may be reusable
```

`reuse_hint` is empty string when no prior work was identified. It is stored in the DB and injected into the agent's task prompt at execution time.

---

## Feature 2: Store Method

### `GoalStore.list_completed_milestone_summaries()`

```python
# ze_personal/goals/store.py

async def list_completed_milestone_summaries(
    self,
    days: int = 90,
    limit: int = 20,
    exclude_goal_id: UUID | None = None,
) -> list[PriorMilestoneOutput]:
    """
    Return recently completed milestones across all goals, ordered by completion date
    descending. Excludes the current goal (exclude_goal_id) and milestones with no
    output. Capped at `limit` rows.
    """
    ...
```

### SQL Implementation

```sql
-- ze_personal/goals/postgres.py

SELECT
    m.id            AS milestone_id,
    m.goal_id,
    g.title         AS goal_title,
    m.title         AS milestone_title,
    m.output,
    GREATEST(0, EXTRACT(EPOCH FROM (NOW() - m.completed_at)) / 86400)::int AS completed_days_ago
FROM goal_milestones m
JOIN goals g ON g.id = m.goal_id
WHERE m.status = 'completed'
  AND m.output != ''
  AND m.completed_at > NOW() - ($1 * INTERVAL '1 day')
  AND ($2::uuid IS NULL OR m.goal_id != $2)
ORDER BY m.completed_at DESC
LIMIT $3
```

Parameters: `$1 = days`, `$2 = exclude_goal_id`, `$3 = limit`.

The query is cheap: it reads at most `limit` rows from an indexed table column (`completed_at`). Output is truncated to 200 chars in Python after the query to avoid sending large blobs to the planner.

---

## Feature 3: Planner Changes

### Updated `plan()` signature

```python
async def plan(
    self,
    goal: Goal,
    prior_work: list[PriorMilestoneOutput] | None = None,
) -> tuple[list[Milestone], list[VerificationGate]]:
```

When `prior_work` is provided and non-empty, append a prior work block to the prompt before calling the LLM:

```python
if prior_work:
    lines = [
        f"  - \"{p.goal_title}\" → \"{p.milestone_title}\" "
        f"({p.completed_days_ago}d ago): {p.output_snippet}"
        for p in prior_work
    ]
    prompt += "\n\nPRIOR WORK FROM OTHER GOALS:\n" + "\n".join(lines)
```

When `prior_work` is `None` or empty, the prompt is unchanged — existing behavior is preserved.

### Updated `_PLAN_SYSTEM`

Add a new paragraph at the end of the existing system prompt:

```
When a PRIOR WORK FROM OTHER GOALS section is present:
- If a prior milestone's output is directly relevant to a planned milestone (same research
  domain, same data source, same type of document), set "reuse_hint" on that milestone.
- Hint format: "Prior goal '[title]' already produced [brief description] ([N] days ago). 
  Retrieve trace before re-running — reuse if still current."
- If the prior work is likely stale for this domain (job listings, company headcounts,
  market prices), add: "Note: may be outdated."
- Only set reuse_hint when there is clear, specific overlap. Do not force hints for vague
  thematic similarity.
- If nothing is reusable, omit reuse_hint or set it to null.
```

### Updated `_parse_plan`

```python
Milestone(
    goal_id=goal_id,
    title=item["title"],
    description=item["description"],
    sequence=item["sequence"],
    agent_hint=item.get("agent_hint"),
    intent=item.get("intent", "execute"),
    status=MilestoneStatus.PENDING,
    reuse_hint=item.get("reuse_hint") or "",   # new
)
```

### Updated `replan_remaining()` signature

```python
async def replan_remaining(
    self,
    goal: Goal,
    completed_milestones: list[Milestone],
    feedback: str,
    next_sequence: int,
    prior_work: list[PriorMilestoneOutput] | None = None,   # new
) -> tuple[list[Milestone], list[VerificationGate]]:
```

Same prior work injection as in `plan()` — append to the prompt if provided.

---

## Feature 4: Execution-Time Hint Display

### `_build_milestone_prompt` change

```python
# ze_personal/goals/executor.py

def _build_milestone_prompt(
    milestone: Milestone,
    goal: Goal,
    all_milestones: list[Milestone],
) -> str:
    ...
    prompt = (
        f"[GOAL CONTEXT]\n"
        ...
        f"[YOUR TASK]\n"
        f"{milestone.description}"
    )
    if milestone.reuse_hint:
        prompt += f"\n\n[PRIOR WORK FROM OTHER GOALS]\n{milestone.reuse_hint}"
    return prompt
```

The hint is appended after the task description so it doesn't interrupt the primary instruction. The agent reading the prompt can then call `get_milestone_trace` (already available as a tool on `GoalAgent`) to retrieve the full prior output before deciding whether to proceed.

---

## Feature 5: Call Sites

### `create_goal` tool

```python
# ze_personal/agents/goals/tools.py

async def create_goal(
    store: GoalStore,
    planner: GoalPlanner,
    ...
) -> dict:
    goal = Goal(...)

    prior_work = await store.list_completed_milestone_summaries(
        days=90,
        limit=20,
        exclude_goal_id=None,   # goal not yet saved, no ID to exclude
    )

    try:
        milestones, gates = await planner.plan(goal, prior_work=prior_work or None)
    except GoalPlanError as exc:
        return {"error": f"Couldn't plan the goal: {exc}"}
    ...
```

The query runs before `store.create_goal(goal)` so the goal has no ID yet — `exclude_goal_id` is `None`. This is correct: there are no milestones from this goal to exclude.

### Executor replan paths

Three call sites in `executor.py` call `replan_remaining`. Each must query prior work and pass it:

**`_apply_steer`** (user steering a running goal):
```python
prior_work = await self._store.list_completed_milestone_summaries(
    days=90, limit=20, exclude_goal_id=goal_id,
)
new_milestones, new_gates = await self._planner.replan_remaining(
    goal, completed, instruction, next_seq, prior_work=prior_work or None,
)
```

**`_trigger_adaptive_replan`** (consecutive failure replan):
```python
prior_work = await self._store.list_completed_milestone_summaries(
    days=90, limit=20, exclude_goal_id=goal_id,
)
new_milestones, new_gates = await self._planner.replan_remaining(
    goal, completed_milestones, "", next_sequence, prior_work=prior_work or None,
)
```

**`handle_gate_redirected`** (user redirect at a gate):
```python
prior_work = await self._store.list_completed_milestone_summaries(
    days=90, limit=20, exclude_goal_id=goal_id,
)
new_milestones, new_gates = await self._planner.replan_remaining(
    goal, completed, feedback, next_seq, prior_work=prior_work or None,
)
```

In all three cases, `exclude_goal_id` is the current goal's ID to avoid Ze treating its own prior milestones as external prior work.

---

## Database Schema

```sql
-- migrations/0NN_milestone_reuse_hint.sql

ALTER TABLE goal_milestones ADD COLUMN reuse_hint TEXT NOT NULL DEFAULT '';
```

No new tables. No index needed — `reuse_hint` is read only during milestone execution (single row lookup by milestone_id, already indexed).

---

## Interface Contract

### `GoalStore.list_completed_milestone_summaries(days, limit, exclude_goal_id) -> list[PriorMilestoneOutput]`

- Returns at most `limit` rows ordered by `completed_at DESC`.
- Excludes milestones with empty output.
- Excludes milestones from `exclude_goal_id` when provided.
- Never raises — DB errors propagate to the caller.
- Output snippets truncated to 200 chars in the Python implementation.

### `GoalPlanner.plan(goal, prior_work=None) -> tuple[list[Milestone], list[VerificationGate]]`

- `prior_work=None` or `prior_work=[]` → identical behavior to current implementation.
- `prior_work` non-empty → planner prompt extended with prior work block.
- Milestones may have non-empty `reuse_hint` if the planner identified overlap.
- `reuse_hint` is never guaranteed — the LLM may find no relevant prior work even when prior_work is provided.

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| `list_completed_milestone_summaries` raises (DB error) | Exception propagates to `create_goal` tool; tool returns `{"error": ...}`. Does not silently swallow. |
| No prior work found (empty list) | `prior_work=None` passed to planner; prompt unchanged; planner behaves as today |
| LLM returns `reuse_hint` for a milestone where no overlap exists | Advisory only — agent is not obligated to use it. Worst case: agent spends 5s checking a trace that isn't useful |
| LLM sets `reuse_hint` on every milestone indiscriminately | The prompt instructs specificity; if this happens in practice, tighten the system prompt instruction |
| Prior milestone output is stale (> 60 days, rapidly-changing domain) | `completed_days_ago` is in the hint; LLM notes staleness. Agent can re-run if it judges the data outdated |
| `goal_execution_traces` is empty for the referenced milestone | `get_milestone_trace` tool returns empty result; agent proceeds without prior output |
| `reuse_hint` is very long (LLM over-generates) | `_parse_plan` can truncate: `item.get("reuse_hint", "")[:300]` |

---

## Implementation Notes

- **No new LLM calls** — the prior work section is injected into the existing `plan()` prompt. This phase adds zero additional LLM round-trips.
- **Existing `get_milestone_trace` tool** (added in Phase 23) is the retrieval mechanism. The agent already knows how to call it. No new tools needed.
- **`prior_work=None` vs `prior_work=[]`**: pass `None` when the list is empty to make the no-prior-work case explicit to the planner. The prompt injection is skipped for both, but `None` is the canonical "no context provided" signal.
- **Why 90 days, limit 20?** 90 days covers most goal lifecycles without including research that is clearly stale. Limit 20 keeps the prompt addition bounded at ~4000 chars worst case (20 × 200 chars), well within the model's context window and unlikely to dominate the planning prompt.
- **`exclude_goal_id` in replanning**: when replanning a running goal, we exclude the current goal's milestones to avoid Ze treating its own completed steps as external prior work. The goal's own prior milestones are already surfaced in the `completed_summary` section of `replan_remaining()`.
- **No change to `ze_core`**: `_build_milestone_prompt` is defined in `ze_personal/goals/executor.py`, not in `ze_core`. The `reuse_hint` field on `Milestone` is a `ze_personal` type. Nothing in `ze_core` needs to change.
- **Backward compatibility**: `reuse_hint` defaults to `""`. Existing milestones (DB rows without the column before migration) get `DEFAULT ''`. The `_build_milestone_prompt` check `if milestone.reuse_hint:` is a no-op for the empty string.

---

## Testing

| Test | Location |
|------|----------|
| `list_completed_milestone_summaries` returns rows within window, ordered by recency | `tests/goals/test_store.py` |
| `list_completed_milestone_summaries` excludes the specified goal_id | `tests/goals/test_store.py` |
| `list_completed_milestone_summaries` excludes milestones with empty output | `tests/goals/test_store.py` |
| `list_completed_milestone_summaries` respects limit | `tests/goals/test_store.py` |
| `GoalPlanner.plan()` with empty prior_work sends unchanged prompt | `tests/goals/test_planner.py` |
| `GoalPlanner.plan()` with prior_work appends prior work block to prompt | `tests/goals/test_planner.py` |
| `_parse_plan` reads `reuse_hint` from LLM JSON output | `tests/goals/test_planner.py` |
| `_parse_plan` defaults `reuse_hint` to `""` when field absent | `tests/goals/test_planner.py` |
| `GoalPlanner.replan_remaining()` with prior_work appends prior work block | `tests/goals/test_planner.py` |
| `_build_milestone_prompt` appends [PRIOR WORK] section when `reuse_hint` set | `tests/goals/test_executor.py` |
| `_build_milestone_prompt` omits [PRIOR WORK] section when `reuse_hint` empty | `tests/goals/test_executor.py` |
| `create_goal` tool calls `list_completed_milestone_summaries` before planning | `tests/agents/goals/test_goal_agent.py` |
| `create_goal` tool passes prior_work to `planner.plan()` | `tests/agents/goals/test_goal_agent.py` |
| `_apply_steer` passes prior_work to `replan_remaining` | `tests/goals/test_executor.py` |
| `_trigger_adaptive_replan` passes prior_work to `replan_remaining` | `tests/goals/test_executor.py` |
| `handle_gate_redirected` passes prior_work to `replan_remaining` | `tests/goals/test_executor.py` |

---

## Open Questions

- [ ] **Hint truncation**: should `_parse_plan` truncate `reuse_hint` at a fixed length (e.g. 300 chars) to prevent over-generated hints from bloating the milestone prompt? Low risk given the system prompt instructs brevity — add if it proves necessary in practice.
- [ ] **Should `list_completed_milestone_summaries` be called inside `GoalPlanner` directly?** Alternative: planner accepts the store as a constructor arg and queries it internally. This would centralise the prior work logic. Rejected for now: planner is currently stateless (takes a client + model), and having it call the store mixes concerns. The call site pattern (tool/executor queries, passes to planner) is more testable.
