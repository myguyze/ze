# Cross-Goal Learning Promotion — Spec

> **Package:** `ze_personal` (planner, executor), `ze_core` (MemoryStore interface, unchanged)
> **Phase:** 28
> **Status:** Done
> **Depends on:** Phase 24 ([32-goal-collaboration.md](../032-goal-collaboration/spec.md)), Phase 5 ([13-phase5-memory.md](../013-phase5-memory/spec.md))

---

## Purpose

Every completed goal accumulates `GoalLearning` records — observations about what worked, what failed, and what Ze discovered during execution. These learnings are goal-scoped: they inform the retrospective narrative and the planner's adaptive replanning, but they never leave the goal. When the goal closes, the learnings close with it.

Some learnings are genuinely goal-specific ("company X uses Salesforce") and shouldn't escape. But others are generalizable: a preference Ze observed about how João likes email drafted, a strategy that proved effective across the goal's domain, a pattern in how João makes decisions. These are exactly the kind of user facts the memory system was designed to hold — but today they remain siloed inside the goal that produced them.

This phase extracts generalizable facts from goal learnings at completion time and promotes them to user memory via the existing `MemoryStore.propose_facts()` path. Promoted facts enter memory as `reviewed=False` — they are visible via `/memory` but go through the normal consolidation pipeline before being treated as canonical. Ze never silently promotes — the user can inspect and reject promoted facts the same way they can reject any agent-proposed fact.

---

## Responsibilities

- At goal completion, after `_push_retrospective` saves the retrospective narrative, run a new promotion step.
- Pass the goal's `GoalLearning` records and goal context to a new `GoalPlanner.promote_learnings()` method.
- Let the planner LLM filter and rewrite generalizable learnings into `UserFact` proposals.
- Submit proposals to `MemoryStore.propose_facts()` — they enter memory as `agent="goals"`, `reviewed=False`.
- Log the number of facts promoted so the feature can be validated in production.
- Never block goal completion or the retrospective push on a promotion failure.

---

## Out of Scope

- **User confirmation before writing** — facts are written as `reviewed=False`, consistent with how every other agent proposes facts. No gate or Telegram prompt is added.
- **Promoting milestone outputs** — raw milestone outputs are too domain-specific and too large. Only `GoalLearning` records (already curated by the LLM at milestone completion) are eligible.
- **Promoting contact or company data** — third-party facts about people or companies belong to the contacts system, not user memory. The promotion prompt explicitly instructs the LLM to exclude these.
- **Semantic dedup before writing** — the Phase 5 consolidation job already handles dedup and contradiction detection across all facts. No extra dedup pass is needed here.
- **Promotion on partial completion** — promotion only fires when `GoalStatus.COMPLETED` is reached. Stopped or failed goals do not trigger promotion; their learnings remain in `goal_learnings` only.
- **Editable promotion results** — the user cannot approve/reject individual promoted facts at the moment they are written. They are visible in `/memory` and will be reviewed through the normal fact lifecycle.

---

## Module Location

```
packages/ze-personal/
  ze_personal/
    goals/
      planner.py        ← add promote_learnings() method + _PROMOTION_SYSTEM prompt
      executor.py       ← add memory_store param to __init__; call _promote_learnings()
                          from _push_retrospective

packages/ze/
  ze/
    container.py        ← pass memory_store to GoalExecutor constructor
```

No new files. No DB schema changes — promoted facts go into the existing `user_facts` table via `propose_facts()`.

---

## Feature 1: New Planner Method

### `GoalPlanner.promote_learnings()`

```python
# ze_personal/goals/planner.py

async def promote_learnings(
    self,
    goal: Goal,
    learnings: list[GoalLearning],
) -> list[UserFact]:
    """
    Extract generalizable user facts from goal learnings.
    Returns an empty list if no generalizable facts are found.
    """
```

#### Prompt construction

```python
learnings_text = "\n".join(
    f"  - [{l.source}] {l.content}" for l in learnings
) or "  (none)"
prompt = (
    f"Goal: {goal.title}\n"
    f"Objective: {goal.objective}\n\n"
    f"Learnings from this goal:\n{learnings_text}"
)
```

#### System prompt

```python
_PROMOTION_SYSTEM = """\
You are extracting generalizable user facts from the learnings of a completed goal.

A generalizable fact is something true about the USER — their preferences, habits,
strategies, decision-making patterns — that applies beyond this specific goal and
would be useful context for future tasks.

A goal-specific learning is NOT a generalizable fact:
  - research about a third-party company, product, or person
  - factual findings about the external world
  - contact details or relationship data
  - anything that is only relevant to this goal's subject matter

Rules:
1. Only extract facts that generalise — user preferences, communication style,
   decision patterns, domain strategies that reflect how the user works.
2. Every fact must be a statement about the USER, not about a third party or the
   external world. The subject of each value must be the user ("prefers...",
   "tends to...", "works best when..."). If the subject is not the user, omit it.
3. Each fact must be written as a short, atomic key-value pair.
4. Produce at most 5 facts. If fewer than 1 generalizable fact exists, return an empty list.
5. Do not fabricate or over-interpret. If a learning is ambiguous, omit it.

Return JSON:
{
  "facts": [
    {"key": "...", "value": "..."},
    ...
  ]
}
If nothing is promotable, return: {"facts": []}
"""
```

#### Parsing

```python
raw = await self._client.complete(
    messages=[{"role": "user", "content": prompt}],
    model=self._model,
    system=_PROMOTION_SYSTEM,
)
try:
    data = json.loads(raw)
    return [
        UserFact(key=f["key"], value=f["value"], agent="goals", reviewed=False)
        for f in data.get("facts", [])
        if isinstance(f.get("key"), str) and isinstance(f.get("value"), str)
    ]
except Exception:
    return []
```

The parser is deliberately permissive — a malformed or empty response returns `[]` without raising. `UserFact` is already imported in `planner.py`; no new imports needed.

---

## Feature 2: Executor Changes

### Updated `GoalExecutor.__init__`

```python
def __init__(
    self,
    goal_store: GoalStore,
    goal_planner: GoalPlanner,
    push: Callable[[Notification], None],
    agent_getter: Callable[[str], object],
    memory_store: MemoryStore | None = None,   # new; optional for backward compat
) -> None:
    ...
    self._memory = memory_store
```

`memory_store` is optional so existing tests that construct `GoalExecutor` directly do not need to be updated. When `None`, promotion is silently skipped.

### New `_promote_learnings()` helper

Accepts `learnings` as a parameter — passed from `_push_retrospective` which already holds them, avoiding a redundant `list_learnings` DB call.

```python
async def _promote_learnings(self, goal: Goal, learnings: list[GoalLearning]) -> None:
    if self._memory is None or not learnings:
        return
    try:
        facts = await self._planner.promote_learnings(goal, learnings)
    except Exception as exc:
        log.warning("goal_learning_promotion_failed", error=str(exc))
        return
    if not facts:
        log.info("goal_learning_promotion_none", goal_id=str(goal.id))
        return
    try:
        await self._memory.propose_facts(facts)
        log.info(
            "goal_learning_promoted",
            goal_id=str(goal.id),
            count=len(facts),
        )
    except Exception as exc:
        log.warning("goal_learning_promotion_write_failed", error=str(exc))
```

### Updated `_push_retrospective()`

Pass `learnings` to `_promote_learnings` — no extra DB call:

```python
async def _push_retrospective(self, goal: Goal, goal_id: UUID) -> None:
    milestones = await self._store.list_milestones(goal_id)
    learnings = await self._store.list_learnings(goal_id)
    try:
        narrative = await self._planner.synthesize_retrospective(goal, milestones, learnings)
    except Exception as exc:
        log.warning("retrospective_failed", error=str(exc))
        narrative = goal.success_condition
    try:
        await self._store.save_retrospective(goal_id, narrative)
    except Exception as exc:
        log.warning("retrospective_save_failed", error=str(exc))
    await self._push(Notification(
        content=(
            f"<b>{_html.escape(goal.title)}</b> — completed\n\n"
            f"{_html.escape(narrative)}"
        ),
        format="html",
        urgency="high",
    ))
    asyncio.create_task(self._promote_learnings(goal, learnings))   # fire-and-forget
```

Promotion runs as a fire-and-forget task so it never delays the retrospective push to the user. A failure in promotion does not surface to the user.

---

## Feature 3: Container Wiring

```python
# ze/container.py

goal_executor = GoalExecutor(
    goal_store=goal_store,
    goal_planner=goal_planner,
    push=notifier.push_notification,
    agent_getter=get_agent,
    memory_store=memory_store,   # new
)
```

`memory_store` is the existing `PostgresMemoryStore` instance already constructed earlier in the container setup.

---

## Interface Contract

### `GoalPlanner.promote_learnings(goal, learnings) -> list[UserFact]`

- Returns 0–5 `UserFact` objects with `agent="goals"`, `reviewed=False`.
- Returns `[]` on any parse or LLM error.
- Never raises.

### `GoalExecutor._promote_learnings(goal, goal_id) -> None`

- Only fires when `self._memory` is not `None`.
- Only fires when the goal has at least one learning.
- Never raises — all exceptions are caught and logged.
- Runs as a fire-and-forget `asyncio.create_task`.

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| `memory_store=None` (tests, backward compat) | `_promote_learnings` returns immediately; no LLM call; no error |
| No learnings on a completed goal | `_promote_learnings` returns immediately |
| LLM returns malformed JSON | `promote_learnings` returns `[]`; no error surfaces |
| LLM returns `{"facts": []}` | `_promote_learnings` logs `goal_learning_promotion_none` and returns |
| `propose_facts` raises (DB error) | Caught; logs `goal_learning_promotion_write_failed`; goal completion unaffected |
| `synthesize_retrospective` fails | `_push_retrospective` already handles this; `_promote_learnings` still runs afterward (uses `list_learnings`, not the narrative) |
| LLM hallucinates facts not grounded in learnings | The promotion prompt instructs specificity; if this occurs in practice, add a `confidence: 0.7` field or tighten the system prompt |

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.memory.store.MemoryStore` | `propose_facts()` — write promoted facts to user memory |
| `ze_core.memory.types.UserFact` | Type for promoted facts |
| `ze_personal.goals.planner.GoalPlanner` | New `promote_learnings()` method |
| `ze_personal.goals.store.GoalStore` | `list_learnings()` — already used in `_push_retrospective` |

---

## Implementation Notes

- **One new LLM call per completed goal.** This is a deliberate cost. Goal completions are infrequent (days to weeks per goal). The promotion call uses the existing `workflow_plan_model`, same as retrospective synthesis.
- **Why fire-and-forget?** Promotion has no user-facing output — the facts appear in the background in `user_facts`. There is no reason to make the retrospective push wait for it. A failure in promotion is a silent degradation, not a user-visible error.
- **Why `agent="goals"`?** The existing `list_recent_facts` and `get_context` queries filter or label facts by agent. Using `"goals"` makes the source traceable in `/memory` output and in consolidation logs.
- **Why optional `memory_store`?** The executor is unit-tested extensively without a real DB. Making `memory_store` optional means zero test changes are required for existing tests — new tests cover the promotion path in isolation.
- **Dedup is free.** The Phase 5 consolidation job (`MemoryConsolidator`) runs periodically and handles semantic dedup across all `user_facts`. A promoted fact that duplicates an existing fact will be merged or marked redundant by the consolidator. No special handling needed here.
- **Learnings are already curated.** `GoalLearning` records are produced by `extract_learning()` — an LLM call that already extracts a concise observation from raw milestone output. The promotion LLM sees pre-filtered text, not raw tool outputs. This significantly reduces hallucination risk.
- **5-fact cap.** The cap is intentional. A goal with 10 milestones could generate 10+ learnings. Promoting all of them would flood `user_facts` with goal-specific noise. The LLM is instructed to find at most 5 and to prefer quality over quantity.

---

## Testing

| Test | Location |
|------|----------|
| `promote_learnings()` with diverse learnings returns only generalizable facts | `tests/goals/test_planner.py` |
| `promote_learnings()` with no generalizable content returns `[]` | `tests/goals/test_planner.py` |
| `promote_learnings()` on malformed LLM JSON returns `[]` without raising | `tests/goals/test_planner.py` |
| `promote_learnings()` caps output at 5 facts | `tests/goals/test_planner.py` |
| `_promote_learnings()` skips when `memory_store=None` | `tests/goals/test_executor.py` |
| `_promote_learnings()` skips when `list_learnings` returns empty | `tests/goals/test_executor.py` |
| `_promote_learnings()` calls `propose_facts` with correct `agent` and `reviewed=False` | `tests/goals/test_executor.py` |
| `_promote_learnings()` swallows `promote_learnings` exceptions | `tests/goals/test_executor.py` |
| `_promote_learnings()` swallows `propose_facts` exceptions | `tests/goals/test_executor.py` |
| `_push_retrospective` fires `_promote_learnings` as a task | `tests/goals/test_executor.py` |
| Existing `_push_retrospective` tests pass without providing `memory_store` | `tests/goals/test_executor.py` |
| `GoalExecutor` constructed with `memory_store=None` behaves identically to current | `tests/goals/test_executor.py` |

---

## Open Questions

- [x] **Should promoted facts be surfaced to the user?** → **No — silent promotion.** Consistent with how every other agent calls `propose_facts`. Facts are inspectable via `/memory`. Surfacing agent-source labels in `/memory` output is a future UX improvement, out of scope here.
- [x] **Should promotion also run after a retrospective on a *stopped* goal?** → **No — completed goals only.** Stopped-goal learnings are partial and lower-signal. The "at least N milestones" threshold adds complexity with unclear payoff. Revisit if real data shows valuable learnings being lost on stops.
- [x] **`workflow_plan_model` or a cheaper model for promotion?** → **Use `workflow_plan_model` for now.** The JSON extraction task is simple and a strong candidate for downgrade to Haiku after cost monitoring (Phase 17) on the first few real goal completions.
