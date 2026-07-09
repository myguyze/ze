# Goal Collaboration — Spec

> **Package:** `ze_core` (state, routing node), `ze_personal` (plugin, executor, planner, tools), `ze` (job)
> **Phase:** 24
> **Status:** Done
> **Depends on:** Phase 23 ([31-goal-engine-v2.md](../031-goal-engine-v2/spec.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| Goal-aware routing (`routing_hints` state field + pre-route node) | ✅ Done |
| `embed_route` consumes `routing_hints` | ✅ Done |
| Conversational steering (steer queue + `steer_goal` tool) | ✅ Done |
| Post-goal retrospective | ✅ Done |
| Weekly progress narrative job | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Phase 23 makes the goal engine contextual, observable, and self-correcting. Phase 24 adds the
collaboration layer: Ze becomes aware of active goals when routing user messages, the user can
steer a running goal at any time via natural Telegram messages, and Ze proactively surfaces goal
progress both at completion and on a weekly cadence.

The central insight: goals are long-running state. Ze should be *continuously aware* that a goal
is executing — not treat each incoming message as arriving in a vacuum. This awareness must live
at the routing layer, not just inside the goals agent.

---

## Responsibilities

- Enrich the routing prompt with active goal and current milestone context before embedding, so
  goal-related messages route correctly without the user needing to say "for my goal."
- Allow the user to steer an active goal via any free-form Telegram message; apply the steer at
  the next milestone boundary without blocking current execution.
- On goal completion, push a synthesized retrospective rather than a terse one-liner.
- On a weekly cadence, push a narrative summary of all active goals and their progress.

---

## Out of Scope

- **Mid-milestone interruption** — aborting a currently-running agentic loop when a steer arrives.
  The next-boundary approach covers all realistic use cases; true mid-execution interrupt adds
  abort token complexity with marginal benefit.
- **Cross-goal awareness** — detecting synergies or conflicts between two concurrent goals.
- **Proactive goal suggestions** — Ze initiating goal creation based on memory patterns.
- **Conversational goal creation** — natural multi-turn goal creation flow (current flow already
  works via `create_goal` tool).

---

## Module Location

```
packages/ze-core/
  ze_core/
    orchestration/
      state.py                         ← add routing_hints field to AgentState
      nodes/routing.py                 ← embed_route reads routing_hints from state

packages/ze-personal/
  ze_personal/
    graph/
      routing_context.py               ← new: inject_goal_routing_context node
    goals/
      executor.py                      ← steer queue, _push_retrospective
      planner.py                       ← synthesize_retrospective()
    agents/goals/
      tools.py                         ← add steer_goal tool
      agent.py                         ← add steer_goal to tools list + instructions
    plugin.py                          ← wire state_extensions, graph_nodes, graph_edges

packages/ze/
  ze/
    jobs/
      goal_narrative.py                ← new: weekly goal progress job
    container.py                       ← register GoalNarrativeJob
    config/config.yaml                 ← add goal_narrative schedule
```

---

## Feature 1: Goal-Aware Routing

### Problem

The `EmbeddingRouter` computes agent description embeddings once at startup into a static matrix.
At route time it encodes only the user's message and finds the closest agent by dot product. A
message like "skip the LinkedIn outreach" contains no signal that associates it with the goals
agent — it will likely route to companion or workflow and the steering intent is lost.

### Design

Add a `routing_hints: str | None` field to `AgentState`. A new graph node
`inject_goal_routing_context`, contributed by `PersonalPlugin`, runs immediately before
`embed_route`. It queries active goals from `GoalStore`, formats a compact hint string, and writes
it to state. `embed_route` in `ze_core` prepends the hints to the routing text before embedding,
with no import from `ze_personal`.

When no goals are active, `routing_hints` is `None` and `embed_route` behaves exactly as today.
The node is a no-op with one cheap DB read.

### Hint Format

```
[Active goals: "Job search outreach" — currently on step 3: LinkedIn outreach campaign | "Learn Spanish" — awaiting gate: Week 1 review]
```

Rules:
- Include only goals in `ACTIVE` or `AWAITING_GATE` status.
- For `ACTIVE` goals: include the title and the current `IN_PROGRESS` or first `PENDING` milestone title.
- For `AWAITING_GATE` goals: include the title and the gate title.
- Cap at 3 goals in the hint (edge case: more than 3 concurrent goals).
- Max hint length: 300 chars. Truncate gracefully if exceeded.

### State Extension

`PersonalPlugin.state_extensions()` returns:

```python
# ze_personal/graph/routing_context.py

from typing import TypedDict
from ze_core.orchestration.state import AgentState

class GoalRoutingState(AgentState):
    routing_hints: str | None
```

### Node

```python
# ze_personal/graph/routing_context.py

async def inject_goal_routing_context(state: AgentState, config: RunnableConfig) -> dict:
    from ze_personal.goals.store import GoalStore

    goal_store: GoalStore | None = config["configurable"].get("goal_store")
    if goal_store is None:
        return {"routing_hints": None}

    hints = await _build_routing_hints(goal_store)
    return {"routing_hints": hints or None}
```

`_build_routing_hints` is a pure-ish async function (one DB call, no LLM). Returns `None` if no
active goals exist.

### Graph Wiring

`PersonalPlugin.graph_edges()` adds the node and edges:

```python
def graph_nodes(self) -> dict:
    from ze_personal.graph.routing_context import inject_goal_routing_context
    return {"inject_goal_routing_context": inject_goal_routing_context}

def graph_edges(self, builder: StateGraph) -> None:
    # Insert before embed_route. The graph builder must expose the START → embed_route
    # edge as replaceable, or plugin edges must use conditional entry logic.
    builder.add_edge("inject_goal_routing_context", "embed_route")
```

**Pre-implementation spike required.** The `ZePlugin.graph_edges()` hook receives the builder
after all base edges have been added. If `START → embed_route` is already wired as a fixed edge,
inserting a new node between them requires either: (a) the graph builder exposes the entry node
as configurable, or (b) a minimal `ze_core` graph_builder change to accept a plugin-supplied
pre-route node. This must be confirmed before implementation begins. If neither is feasible
without significant refactoring, the fallback is to populate `routing_hints` in state before the
graph starts (e.g., in the `ZeContainer.invoke()` call site), which is less elegant but equally
correct.

### `embed_route` Change

```python
# ze_core/orchestration/nodes/routing.py

async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    router: EmbeddingRouter = config["configurable"]["router"]
    routing_text = state.get("image_caption") or state["prompt"]

    hints = state.get("routing_hints")
    if hints:
        # Append hints AFTER the message so the actual message content dominates
        # the embedding. Prepending hint tokens risks misdirecting non-goal messages
        # (e.g. "what's the weather?" becoming goal-adjacent due to leading goal tokens).
        routing_text = f"{routing_text}\n\n{hints}"

    envelope = await router.route(prompt=routing_text, session_id=state["session_id"])
    ...
```

This is the only change to `ze_core`. No import of `ze_personal`.

**Routing accuracy note.** Appending hints after the message reduces but does not eliminate
misdirection risk. For Phase 24, this is acceptable given the single-user context and easy
correction. If misdirection proves problematic in practice, the mitigation is to shorten hints
further (goal title only, no milestone detail) or move hints into a separate low-weight embedding
pass.

---

## Feature 2: Conversational Steering

### Design

At next-milestone-boundary steering: the user's instruction is enqueued when received; before
picking the next milestone, `_advance_unlocked` checks the queue and replans if one is pending.

This is honest about timing: "Got it — I'll apply that after the current step finishes." The user
is not blocked waiting, and Ze does not abort in-flight LLM calls.

### Executor Changes

```python
# ze_personal/goals/executor.py

class GoalExecutor:
    def __init__(self, ...) -> None:
        ...
        self._steer_queues: dict[UUID, asyncio.Queue] = defaultdict(asyncio.Queue)

    async def steer(self, goal_id: UUID, instruction: str) -> bool:
        """Enqueue a steering instruction for the goal. Returns False if goal is not active."""
        goal = await self._store.get_goal(goal_id)
        if goal is None or goal.status not in (GoalStatus.ACTIVE, GoalStatus.AWAITING_GATE):
            return False
        await self._steer_queues[goal_id].put(instruction)
        log.info("goal_steer_queued", goal_id=str(goal_id))
        return True
```

At the top of `_advance_unlocked`, after acquiring the lock but before picking the next milestone:

```python
async def _advance_unlocked(self, goal_id: UUID) -> None:
    goal = await self._store.get_goal(goal_id)
    if goal is None or goal.status != GoalStatus.ACTIVE:
        return

    # Apply any pending steer before picking the next milestone
    if not self._steer_queues[goal_id].empty():
        instruction = self._steer_queues[goal_id].get_nowait()
        await self._apply_steer(goal_id, goal, instruction)
        return  # _apply_steer will create_task(advance) after replanning

    # ... existing milestone selection logic
```

`_apply_steer`:
1. Collect completed milestones.
2. Notify user: "Applying your direction — replanning remaining steps..."
3. Call `self._planner.replan_remaining(goal, completed, instruction, next_seq)`.
4. Replace pending milestones and gates.
5. Reset `consecutive_failures` to 0.
6. `asyncio.create_task(self.advance(goal_id))`.
7. On replan failure: push notification, pause goal.

### Goal Agent Changes

New `steer_goal` tool:

```python
# ze_personal/agents/goals/tools.py

@tool(access="write")
async def steer_goal(
    goal_id: str,
    instruction: str,
    executor: GoalExecutor,
) -> str:
    """
    Redirect a running goal with new instructions. Ze will finish its current step and then
    replan the remaining milestones incorporating your direction.
    Returns a confirmation or an error if the goal is not active.
    """
    ok = await executor.steer(UUID(goal_id), instruction)
    if not ok:
        return "That goal is not currently active. Use list_goals to check status."
    return "Got it — I'll apply that direction after the current step finishes."
```

Add to `GoalAgent.tools` and update `_AGENT_INSTRUCTIONS`:

```
- steer_goal: redirect a running goal with new instructions (goal_id, instruction).
  Use when the user wants to change direction mid-execution without stopping entirely.
  Always call list_goals first if the user hasn't provided a goal_id.
```

### Routing and Intent Detection

With goal-aware routing (Feature 1) in place, messages like "skip the LinkedIn part" now have
active goal context in their routing text and will route to the goals agent reliably.

The goal agent must recognize steering as a distinct intent. Update `intent_map`:

```python
intent_map = {
    "create": "Create a new multi-week goal and decompose it into milestones.",
    "read":   "Inspect goal status, list active goals, or review progress and traces.",
    "update": "Pause, resume, or redirect (steer) an active goal mid-execution.",
    "delete": "Abandon a goal.",
}
```

Steering is a `CONFIRM` capability operation (same as `update`). The goal agent calls
`list_goals` first if the user hasn't named a specific goal, confirms which goal to steer, then
calls `steer_goal`.

---

## Feature 3: Post-Goal Retrospective

### Problem

When all milestones complete, `_advance_unlocked` pushes:
`"Goal <title> is complete!\n\n<success_condition>"` — a terse system message. There is no
synthesis of what was actually accomplished, what was learned, or what comes next.

### New Planner Method

```python
# ze_personal/goals/planner.py

_RETROSPECTIVE_SYSTEM = """\
You write a concise retrospective for a completed goal. Cover three things:
1. What was accomplished (be specific — reference actual outputs, not just milestone titles).
2. Key learnings or insights surfaced during execution.
3. Suggested next steps or follow-on goals, if any.

Write in plain language, 3-5 short paragraphs. No headers. Address the user directly.\
"""

async def synthesize_retrospective(
    self,
    goal: Goal,
    milestones: list[Milestone],
    learnings: list[GoalLearning],
) -> str:
    """Produce a goal completion retrospective."""
    ...
```

Prompt includes goal title, objective, success condition, each milestone's title + output (capped
at 300 chars each), and the last 5 learnings.

### Executor Change

Replace the existing completion push in `_advance_unlocked`:

```python
# Before:
await self._push(Notification(
    content=f"Goal <b>{title}</b> is complete!\n\n<i>{success_condition}</i>",
    format="html",
    urgency="high",
))

# After:
milestones_full = await self._store.list_milestones(goal_id)
learnings = await self._store.list_learnings(goal_id)
try:
    narrative = await self._planner.synthesize_retrospective(goal, milestones_full, learnings)
except Exception as exc:
    log.warning("retrospective_failed", error=str(exc))
    narrative = goal.success_condition  # fallback to terse form

await self._push(Notification(
    content=(
        f"<b>{_html.escape(goal.title)}</b> — completed\n\n"
        f"{_html.escape(narrative)}"
    ),
    format="html",
    urgency="high",
))
```

Retrospective synthesis failure falls back gracefully — goal completion is always pushed.

---

## Feature 4: Weekly Progress Narrative

### Design

A proactive job running on a configurable schedule (default: Sunday 18:00) that synthesizes a
plain-language summary of all active goals and their week's progress.

For each active/awaiting-gate goal, Ze produces one paragraph covering:
- Milestones completed since the last narrative push (queried via `created_at` on
  `goal_milestones`)
- Any gate currently awaiting approval (surfaced prominently — users forget pending gates)
- What's coming next

If no goals are active and no goals completed this week: job is a no-op.

### New Job

```python
# ze/jobs/goal_narrative.py

from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.proactive.push_log_store import PushLogStore
from ze_personal.goals.store import GoalStore
from ze_personal.goals.planner import GoalPlanner

@proactive_job
class GoalNarrativeJob:
    job_id = "goal_narrative"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
    ) -> None: ...

    async def run(self) -> None: ...
```

The job uses `PushLogStore` to deduplicate: skip if `was_sent_within_hours("goal_narrative", 144)`
(6 days — prevents double-send if the job fires twice due to scheduler jitter).

### Narrative Synthesis

One `GoalPlanner` method call per active goal:

```python
# ze_personal/goals/planner.py

async def synthesize_weekly_narrative(
    self,
    goal: Goal,
    completed_this_week: list[Milestone],
    pending_gate: VerificationGate | None,
    next_milestones: list[Milestone],
) -> str:
    """One paragraph: what Ze did this week on this goal, and what comes next."""
    ...
```

The weekly job assembles per-goal paragraphs into a single Telegram message:

```
<b>Goal progress — this week</b>

<b>Job search outreach</b>
Ze completed 3 milestones this week: compiled a target list of 40 companies, drafted outreach
templates, and sent initial emails to 12 contacts. Awaiting your approval at the "First batch
review" checkpoint before continuing to the follow-up sequence.

<b>Learn Spanish (B1)</b>
Ze completed the vocabulary consolidation step. Flashcard deck is ready in Anki. Next up:
first conversation simulation session scheduled for this week.
```

If a goal is `AWAITING_GATE`, the gate is called out explicitly with a reminder to act.

### Config

```yaml
# config/config.yaml
proactive:
  goal_narrative:
    schedule: "0 18 * * 0"   # Sunday 18:00
```

---

## Interface Contract

### `GoalExecutor.steer(goal_id, instruction) -> bool`

Puts `instruction` on `_steer_queues[goal_id]`. Returns `True` if goal is active, `False`
otherwise. Never raises. Called from `steer_goal` tool.

### `GoalPlanner.synthesize_retrospective(goal, milestones, learnings) -> str`

Single LLM completion. May raise `OpenRouterError` — caller catches and falls back.

### `GoalPlanner.synthesize_weekly_narrative(goal, completed_this_week, pending_gate, next_milestones) -> str`

Single LLM completion per goal. Goal narrative job catches all exceptions per goal and skips that
goal's paragraph rather than failing the whole job.

### Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| `inject_goal_routing_context` DB read fails | Returns `{"routing_hints": None}` — routing unaffected |
| Active goal has no current milestone (all pending) | Hint shows goal title only, no "currently on step X" |
| Steer arrives while goal is `AWAITING_GATE` | `steer()` returns `False`; goal agent tells user to resolve the gate first or use `redirect` at the gate |
| Two steer instructions arrive before the queue is consumed | Only the first is consumed by `_advance_unlocked`; the second remains queued for the following advance cycle |
| Ze restarts with a steer queued | Steer is lost (in-memory queue). User must re-send direction. Known limitation — documented in Implementation Notes. |
| Routing hints cause a non-goal message to route to goals agent | Goals agent finds no matching intent and responds naturally; no data is corrupted. If this happens frequently, shorten hint format to title-only. |
| `synthesize_retrospective` fails | Falls back to success condition text; completion notification always fires |
| `synthesize_weekly_narrative` fails for one goal | That goal's paragraph is omitted; other goals still push |
| No goals active at job run time | Job logs and exits; nothing is pushed |
| Graph wiring spike finds no feasible insertion point | Fall back: populate `routing_hints` in `ZeContainer.invoke()` before graph execution. Functionally equivalent; less elegant. |

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.orchestration.state.AgentState` | Add `routing_hints` field |
| `ze_core.orchestration.nodes.routing` | `embed_route` reads `routing_hints` |
| `ze_core.plugin.ZePlugin` | `state_extensions`, `graph_nodes`, `graph_edges` |
| `ze_personal.goals.executor.GoalExecutor` | Steer queue, retrospective push |
| `ze_personal.goals.planner.GoalPlanner` | `synthesize_retrospective`, `synthesize_weekly_narrative` |
| `ze_core.proactive.job` | `@proactive_job` for weekly narrative |
| `ze_core.proactive.push_log_store` | Dedup for weekly narrative |
| No new migrations | No new tables or columns |

---

## Implementation Notes

- `routing_hints` enriches the **routing prompt** (user message), not the agent description
  embeddings. Agent embeddings are computed once at startup and are static. Prepending hints to
  the routing text is the only way to inject runtime context into the embedding comparison without
  recomputing the matrix.
- The steer queue uses `get_nowait()` (not `await queue.get()`) in `_advance_unlocked` because the
  lock is already held — blocking would deadlock if `steer()` is called from within the same event
  loop iteration.
- **Known limitation: steer queue is not persisted.** `_steer_queues` is an in-memory
  `asyncio.Queue`. If Ze restarts while a steer is queued, the instruction is silently lost. The
  user will need to re-send their direction after noticing the goal continued unchanged. This is
  acceptable for Phase 24 given restart frequency. A future phase can persist pending steers to a
  `goal_steers` DB table. The weekly narrative job and gate notifications serve as natural
  reminders that prompt the user to re-engage with active goals.
- `GoalPlanner.synthesize_weekly_narrative` is called once per active goal, not once for all goals
  combined. This keeps individual calls cheap and allows graceful per-goal failure.
- Steer is `CONFIRM` capability mode because it replans and resumes execution — a consequential
  write operation. The goal agent will ask for confirmation before calling `steer_goal` if the
  gate decision requires it.

---

## Testing

| Test | Location |
|---|---|
| `inject_goal_routing_context` with active goals returns formatted hints | `tests/goals/test_routing_context.py` |
| `inject_goal_routing_context` with no active goals returns `None` | `tests/goals/test_routing_context.py` |
| `embed_route` prepends hints when `routing_hints` is set | `tests/orchestration/test_routing_node.py` |
| `embed_route` is unchanged when `routing_hints` is `None` | `tests/orchestration/test_routing_node.py` |
| `GoalExecutor.steer` enqueues instruction for active goal | `tests/goals/test_executor.py` |
| `GoalExecutor.steer` returns `False` for non-active goal | `tests/goals/test_executor.py` |
| `_advance_unlocked` drains steer queue before next milestone | `tests/goals/test_executor.py` |
| `_apply_steer` replans and resumes execution | `tests/goals/test_executor.py` |
| `synthesize_retrospective` failure → completion message still fires | `tests/goals/test_executor.py` |
| `GoalNarrativeJob.run` skips when no active goals | `tests/jobs/test_goal_narrative.py` |
| `GoalNarrativeJob.run` deduplicates within 6 days | `tests/jobs/test_goal_narrative.py` |
| `steer_goal` tool returns error for non-active goal | `tests/agents/goals/test_goal_agent.py` |

---

## Open Questions

- [x] Should steer apply at next-boundary or interrupt current milestone? → **Next-boundary.** True interruption requires abort tokens threaded through the agentic loop, with no meaningful UX benefit for the common case.
- [x] Should `routing_hints` be in `AgentState` (ze_core) or a plugin state extension? → **`AgentState` directly**, since `embed_route` in `ze_core` reads it. Adding it as a plugin extension would require `ze_core` to do `state.get("routing_hints")` with a fallback anyway, making the state_extension approach fragile. A clean field on `AgentState` is simpler.
- [x] Should steer work while goal is `AWAITING_GATE`? → **No.** The gate is a deliberate pause for human review. Steering while awaiting a gate bypasses the review intent. The goal agent tells the user to resolve the gate first (approve/stop/redirect), then steer if needed.
- [x] Should hints be prepended or appended to the routing text? → **Appended.** Prepending goal tokens before the user's message risks misdirecting non-goal messages by front-loading goal-adjacent vocabulary. Appending preserves the message's natural embedding dominance.
- [x] Can the steer queue loop if multiple steers are queued? → **No.** `_advance_unlocked` drains exactly one steer per advance cycle. Each steer triggers a replan and re-advance; subsequent steers are consumed in the next cycle. This is correct — each steer should produce one replan.
- [ ] **Spike needed:** Confirm `ZePlugin.graph_edges()` can insert `inject_goal_routing_context` before `embed_route`. If not, implement fallback via `ZeContainer.invoke()` instead. Must be resolved before Feature 1 implementation begins.
