# Cross-Goal Awareness: Proactive Surfacing & Convergence Detection — Spec

> **Package:** `ze_personal` (types, planner, executor, tools)
> **Phase:** 71
> **Status:** Pending
> **Depends on:** Phase 35 ([35-cross-goal-output-reuse.md](../035-cross-goal-output-reuse/spec.md)), Phase 36 ([36-cross-goal-learning-promotion.md](../036-cross-goal-learning-promotion/spec.md))

---

## Purpose

Phases 35 and 36 gave Ze the machinery to reuse prior goal outputs and promote
learnings — silently. Ze identifies overlapping prior work at planning time, embeds
a `reuse_hint`, and the agent may act on it — but the user never knows this happened.
Similarly, two concurrent active goals may be working toward the same outcome with no
one noticing until both have spent significant effort.

This phase makes Ze's cross-goal intelligence visible in two ways:

1. **Convergence detection** — when a new goal is created, Ze checks whether any
   active goals overlap in objective or domain and tells the user, offering options.
2. **Proactive reuse surfacing** — when a milestone with a `reuse_hint` completes,
   Ze notifies the user that it leveraged prior work from another goal and what was
   carried over.

Both features are informational: they surface Ze's reasoning and give the user
context; no automatic merging, pausing, or skipping occurs without user instruction.

---

## Responsibilities

- At `create_goal` time, detect whether any active goals share meaningful scope or
  objective with the new goal and push a convergence notice if so.
- After a milestone with a `reuse_hint` completes, push a reuse notice naming the
  source goal and what was reused.
- Keep both flows non-blocking: the goal is created and milestones are executed
  regardless of convergence or reuse outcomes.
- Never surface false-positive convergence (vague thematic similarity) — require
  the LLM to identify specific, concrete overlap before notifying.

---

## Out of Scope

- **Goal merging** — automatically combining two convergent goals. The user must
  instruct Ze to merge; Ze cannot do so autonomously.
- **Pausing one goal** — not triggered automatically; the user decides after the
  convergence notice.
- **Reuse confirmation** — the user is not asked to approve reuse before it happens.
  The notice is after the fact (milestone completed), not a gate.
- **Convergence on completed goals** — we only check active goals. A completed
  goal is surfaced via `reuse_hint` (Phase 35), not convergence detection.
- **Convergence check on replan** — only fires at initial goal creation.
- **Inline correlation across all signals** — that is Phase 58. This spec is
  goal-scoped only.

---

## Module Location

```
plugins/ze-personal/
  ze_personal/
    goals/
      types.py      ← add GoalConvergence dataclass
      planner.py    ← add detect_convergence() method + _CONVERGENCE_SYSTEM prompt
      executor.py   ← add reuse notification in _execute_milestone
    agents/goals/
      tools.py      ← call detect_convergence in create_goal; push convergence notice
```

No new files. No DB schema changes.

---

## Feature 1: Goal Convergence Detection

### New type

```python
# ze_personal/goals/types.py

@dataclass
class GoalConvergence:
    overlapping_goal_id: UUID
    overlapping_goal_title: str
    overlap_description: str   # one sentence: what the goals share
    suggestion: str            # "share outputs", "sequence them", or "keep independent"
```

### New planner method

```python
# ze_personal/goals/planner.py

async def detect_convergence(
    self,
    new_goal: Goal,
    active_goals: list[Goal],
) -> GoalConvergence | None:
    """
    Check whether the new goal meaningfully overlaps with any active goal.
    Returns the most significant convergence if found, or None.
    Never raises — parse errors and LLM failures return None.
    """
```

#### Prompt construction

```python
active_lines = "\n".join(
    f"  - id={g.id} title={g.title!r} objective={g.objective!r}"
    for g in active_goals
)
prompt = (
    f"New goal:\n"
    f"  title: {new_goal.title!r}\n"
    f"  objective: {new_goal.objective!r}\n"
    f"  success_condition: {new_goal.success_condition!r}\n\n"
    f"Active goals:\n{active_lines}"
)
```

#### System prompt

```python
_CONVERGENCE_SYSTEM = """\
You detect whether a newly created goal meaningfully overlaps with an existing active goal.

Meaningful overlap means: the goals share research domain, target the same external
parties, produce the same type of artifact, or would clearly benefit from sharing work.
Vague thematic similarity ("both are about business") is NOT overlap.

If you find meaningful overlap, return:
{
  "overlapping_goal_id": "<uuid of the most overlapping active goal>",
  "overlapping_goal_title": "<title of that goal>",
  "overlap_description": "<one sentence: what specifically the goals share>",
  "suggestion": "<one of: 'share outputs', 'sequence them', 'keep independent'>"
}

If there is no meaningful overlap, return: {"overlap": null}

Rules:
- Only report overlap when it is specific and concrete.
- Pick at most one overlapping goal (the one with the highest overlap).
- The suggestion should reflect what Ze would most naturally do given the overlap
  type: 'share outputs' if they produce the same type of work, 'sequence them' if
  one logically precedes the other, 'keep independent' if overlap is minor.
- Do not fabricate overlap. If in doubt, return null.
"""
```

#### Parsing

```python
raw = await self._client.complete(
    messages=[{"role": "user", "content": prompt}],
    model=self._model,
    system=_CONVERGENCE_SYSTEM,
)
try:
    data = json.loads(raw)
    if not data.get("overlapping_goal_id"):
        return None
    return GoalConvergence(
        overlapping_goal_id=UUID(data["overlapping_goal_id"]),
        overlapping_goal_title=data["overlapping_goal_title"],
        overlap_description=data["overlap_description"][:300],
        suggestion=data["suggestion"][:100],
    )
except Exception:
    return None
```

### `create_goal` tool changes

After planning succeeds and the goal is saved, run convergence detection and push
a notification if overlap is found:

```python
# ze_personal/agents/goals/tools.py

async def create_goal(...) -> dict:
    ...
    # existing: plan + save goal

    # convergence check (after save so goal_id exists, but non-blocking)
    asyncio.create_task(_check_convergence(store, planner, push, goal, active_goals))

    return {"goal_id": str(goal.id), ...}


async def _check_convergence(
    store: GoalStore,
    planner: GoalPlanner,
    push: Callable[[Notification], None],
    new_goal: Goal,
    active_goals: list[Goal],
) -> None:
    # active_goals is fetched before goal creation; filter out the new goal just in case
    others = [g for g in active_goals if g.id != new_goal.id]
    if not others:
        return
    try:
        conv = await planner.detect_convergence(new_goal, others)
    except Exception as exc:
        log.warning("goal_convergence_check_failed", error=str(exc))
        return
    if conv is None:
        return
    log.info(
        "goal_convergence_detected",
        new_goal_id=str(new_goal.id),
        overlapping_goal_id=str(conv.overlapping_goal_id),
    )
    push(Notification(
        content=(
            f"<b>Goal overlap detected</b>\n\n"
            f"<b>{_html.escape(new_goal.title)}</b> and "
            f"<b>{_html.escape(conv.overlapping_goal_title)}</b> share scope: "
            f"{_html.escape(conv.overlap_description)}\n\n"
            f"Suggested approach: <i>{_html.escape(conv.suggestion)}</i>. "
            f"Let me know if you'd like to share outputs between them, sequence one "
            f"after the other, or keep them running independently."
        ),
        format="html",
        urgency="normal",
    ))
```

The `active_goals` list must be fetched before `store.create_goal()` is called so
that the new goal is not included in the convergence check's candidate set. The tool
already calls `store.list_active()` for the routing guard — reuse that result.

---

## Feature 2: Proactive Reuse Notification

When a milestone that had a `reuse_hint` completes successfully, Ze tells the user
what was carried over and from which goal.

### `executor.py` change

In `_execute_milestone`, after `update_milestone(status=COMPLETED)`, add:

```python
if milestone.reuse_hint:
    asyncio.create_task(
        self._push_reuse_notice(goal, milestone)
    )
```

### New executor helper

```python
async def _push_reuse_notice(self, goal: Goal, milestone: Milestone) -> None:
    log.info(
        "goal_reuse_notice_sent",
        goal_id=str(goal.id),
        milestone_title=milestone.title,
    )
    self._push(Notification(
        content=(
            f"<b>Prior work reused</b>\n\n"
            f"While completing <i>{_html.escape(milestone.title)}</i> "
            f"(goal: <b>{_html.escape(goal.title)}</b>), I drew on earlier work "
            f"from another goal:\n\n"
            f"{_html.escape(milestone.reuse_hint)}"
        ),
        format="html",
        urgency="low",
    ))
```

The `reuse_hint` field already contains the source goal name and overlap description
(written by the planner in Phase 35), so no additional DB lookup is needed.

---

## Interface Contract

### `GoalPlanner.detect_convergence(new_goal, active_goals) -> GoalConvergence | None`

- Returns `None` when `active_goals` is empty.
- Returns `None` on any LLM or parse error.
- Returns `None` when the LLM finds no meaningful overlap.
- Returns at most one `GoalConvergence` (the highest-overlap active goal).
- Never raises.

### `create_goal` tool convergence path

- Convergence check runs as `asyncio.create_task` — goal creation response is
  returned to the user before the check completes.
- A push notification is sent if and only if `detect_convergence` returns non-None.
- Failure in the convergence task is caught and logged; goal creation is unaffected.

### `_push_reuse_notice`

- Only fires when `milestone.reuse_hint` is non-empty.
- Runs as `asyncio.create_task` — does not delay milestone execution.
- Always sends the notification (no additional filtering).

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| `detect_convergence` raises | Caught in `_check_convergence`; logs warning; no notification; goal creation proceeds |
| LLM returns malformed JSON | `detect_convergence` returns `None` |
| LLM returns `{"overlap": null}` | `detect_convergence` returns `None` |
| LLM over-reports convergence (false positive) | Tighten `_CONVERGENCE_SYSTEM` prompt; surfacing bar is in the prompt |
| `active_goals` list is empty at creation time | `_check_convergence` returns early; no LLM call |
| Milestone `reuse_hint` is set but agent chose not to use prior work | Notification fires anyway — Ze identified real overlap at planning time; the hint is accurate regardless of how the agent resolved it |
| `push` callable raises | Not caught — same as any other notification failure in the executor |

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_personal.goals.planner.GoalPlanner` | New `detect_convergence()` method |
| `ze_personal.goals.store.GoalStore` | `list_active()` — already called in `create_goal` |
| `ze_personal.goals.types.GoalConvergence` | New type for convergence result |
| `ze_agents.interface.types.Notification` | Push notification to user |

---

## Implementation Notes

- **One new LLM call per goal creation** when active goals exist. Goal creation is
  infrequent; the cost is acceptable.
- **`active_goals` prefetch**: the `create_goal` tool must call `store.list_active()`
  before `store.create_goal()` so the new goal is not in the candidate set. Check
  whether the existing call site already does this and move it earlier if needed.
- **Urgency levels**: convergence notice uses `urgency="normal"` (user should see
  it promptly but it is not critical); reuse notice uses `urgency="low"` (background
  information, no action required).
- **Reuse notice fires on completion only**: if a milestone fails and is retried,
  the notice fires when and if the milestone eventually completes. It does not fire
  on failure.
- **No new DB columns**: `GoalConvergence` is ephemeral (computed at creation time,
  surfaced via notification). The `reuse_hint` already persists on the `Milestone`
  row — no new storage needed.
- **Why fire-and-forget for both?** Neither the convergence check nor the reuse
  notification should delay the critical path (goal creation response or milestone
  completion). Both are informational; a failure in either should not surface to
  the user.

---

## Testing

| Test | Location |
|------|----------|
| `detect_convergence` with overlapping active goals returns `GoalConvergence` | `tests/goals/test_planner.py` |
| `detect_convergence` with no meaningful overlap returns `None` | `tests/goals/test_planner.py` |
| `detect_convergence` with empty active list returns `None` without LLM call | `tests/goals/test_planner.py` |
| `detect_convergence` on LLM parse error returns `None` without raising | `tests/goals/test_planner.py` |
| `_check_convergence` pushes notification when convergence found | `tests/agents/goals/test_goal_agent.py` |
| `_check_convergence` does not push when `detect_convergence` returns None | `tests/agents/goals/test_goal_agent.py` |
| `_check_convergence` swallows `detect_convergence` exceptions | `tests/agents/goals/test_goal_agent.py` |
| `_push_reuse_notice` pushes notification with `reuse_hint` content | `tests/goals/test_executor.py` |
| `_push_reuse_notice` not called when `reuse_hint` is empty | `tests/goals/test_executor.py` |
| `_execute_milestone` spawns reuse notice task on completion with hint set | `tests/goals/test_executor.py` |
| Existing `create_goal` tests pass unchanged | `tests/agents/goals/test_goal_agent.py` |

---

## Open Questions

- [x] **Should convergence fire on replan?** → No. Only at initial goal creation. Replanning is goal-internal; adding a convergence check at replan time would be noisy and rarely actionable.
- [x] **Should the reuse notice include the full hint or a summary?** → Full hint. The `reuse_hint` field is already capped at 300 chars (Phase 35) and is human-readable narrative. No additional summarization needed.
- [x] **Should convergence be surfaced as a confirmation (blocking) rather than a notification?** → No. Blocking goal creation on a convergence check adds latency and friction. The user can act on the notice via a follow-up message ("merge them", "pause the older one"). Confirmations are for irreversible actions; this is informational.
- [x] **What if the same convergence fires every time a goal is created?** → The LLM is prompted to return null when overlap is not specific. If false positives are a real problem, add a `last_convergence_notice_at` guard on the overlapping goal (similar to `last_stuck_alert_at` on `Goal`). Defer until observed.
