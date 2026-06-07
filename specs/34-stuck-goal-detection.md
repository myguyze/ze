# Stuck Goal Detection — Spec

> **Package:** `ze_personal` (store, types), `ze` (job, Telegram callbacks)
> **Phase:** 26
> **Status:** Pending
> **Depends on:** Phase 19 (28-goal-engine.md), Phase 23 (31-goal-engine-v2.md), Phase 24 (32-goal-collaboration.md)

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `StuckGoal` type | 🔲 Pending |
| `GoalStore.list_stuck()` + `mark_stuck_alerted()` | 🔲 Pending |
| Migration: `last_stuck_alert_at` on `goals` | 🔲 Pending |
| `StuckGoalJob` (weekly cron, no LLM) | 🔲 Pending |
| Telegram callback handler (`goal_stuck:*`) | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

Ze executes goals autonomously over multiple weeks, but has no mechanism to notice when
a goal has stalled and the user's attention is needed. Two situations cause this:

1. **AWAITING_GATE for too long** — Ze sent a verification gate notification to Telegram
   (approve/redirect/stop), but the user dismissed or forgot the message. The goal sits
   waiting indefinitely. This is the primary real-world case.

2. **ACTIVE with no milestone progress** — Ze is trying (the executor sweep runs every
   15 minutes), but no milestone has completed in 7 days. Because the failure handling
   path pauses goals quickly (2 consecutive failures → adaptive replan → pause after a
   second round of failures), this is rare in normal operation. It indicates an edge case
   such as milestones completing with trivial or empty output that Ze doesn't treat as
   failure, or a long-running DB anomaly.

In both cases the user has no visibility without manually checking `/goals`. This phase
adds a weekly proactive check that surfaces stuck goals in a single consolidated
Telegram message with inline actions.

---

## Responsibilities

- On a weekly schedule, identify ACTIVE goals with no milestone progress in ≥ 7 days
  and AWAITING_GATE goals whose pending gate has been idle for ≥ 7 days.
- Exclude goals alerted within the past 14 days to prevent notification spam.
- Send one consolidated Telegram message listing all stuck goals with per-goal context
  (last completed milestone or gate title).
- Provide inline keyboard actions per goal:
  - ACTIVE stuck: **Redirect** / **Pause** / **Abandon**
  - AWAITING_GATE stuck: **Approve** / **Redirect** / **Stop**
- Execute actions atomically on callback receipt; remove keyboard on resolution.
- Record `last_stuck_alert_at` on the goal row after each alert so the 14-day cooldown
  applies correctly.
- Never fire if no goals qualify; never call `executor.advance()` (the 15-minute sweep
  already does this continuously — adding another call in the job would be redundant).

---

## Out of Scope

- **Auto-retry / self-heal** — the executor sweep (`*/15 * * * *`) already calls
  `advance()` for all ACTIVE goals continuously. By the time the weekly job fires, any
  restart-caused stuckness would have self-healed. Calling `advance()` in the job adds
  nothing.
- **PAUSED goal reminders** — Ze already sends an explicit notification when it pauses a
  goal. The user knows; no follow-up needed from this job.
- **Cross-goal conflict or overlap detection** — a qualitatively different problem
  (semantic reasoning across goal boundaries). Deferred to a future spec.
- **Configurable staleness threshold per goal** — unnecessary for a single user.
- **Inline redirect flow (ForceReply)** — the redirect action emits a short prompt
  telling the user to message Ze with new instructions. Phase 24's goal-aware routing
  then picks up the next natural message. No ForceReply state needed.

---

## Module Location

```
packages/ze-personal/
  ze_personal/
    goals/
      types.py          ← add StuckGoal dataclass
      store.py          ← add list_stuck(), mark_stuck_alerted() to protocol
      postgres.py       ← implement both methods

packages/ze/
  ze/
    jobs/
      stuck_goals.py    ← new: StuckGoalJob (@proactive_job)
    telegram/
      bot.py            ← add goal_stuck:* callback handler
    migrations/
      0NN_stuck_goals.sql ← ALTER TABLE goals ADD COLUMN last_stuck_alert_at
    config/
      config.yaml       ← add stuck_goals schedule
```

---

## Feature 1: Data Types

### `StuckGoal`

```python
# ze_personal/goals/types.py

from typing import Literal

@dataclass
class StuckGoal:
    goal: Goal
    kind: Literal["active", "awaiting_gate"]
    idle_days: int                       # days since last milestone activity (or gate fire)
    last_milestone_title: str | None     # most recently completed/skipped milestone, if any
    gate: VerificationGate | None        # set iff kind == "awaiting_gate"
```

`StuckGoal` is a read-only view computed at query time. It is never persisted — it exists
solely to carry the context needed to build the Telegram message without additional
per-goal queries in the job.

### `Goal` — new field

```python
# ze_personal/goals/types.py

@dataclass
class Goal:
    ...
    last_stuck_alert_at: datetime | None = None    # ← new
```

---

## Feature 2: Store Methods

### `GoalStore` protocol additions

```python
# ze_personal/goals/store.py

async def list_stuck(
    self,
    idle_days: int,
    alert_cooldown_days: int,
) -> list[StuckGoal]:
    """
    Return all goals that qualify as stuck, ready for the weekly alert.

    A goal qualifies when ALL of the following hold:
      - status is 'active' or 'awaiting_gate'
      - no milestone has been completed or skipped within the last `idle_days` days
        (for 'active'); or the pending gate has been idle for `idle_days` days
        (for 'awaiting_gate')
      - last_stuck_alert_at is NULL or older than `alert_cooldown_days` days

    Returns a list of StuckGoal with computed idle_days, last_milestone_title,
    and gate populated. Results are ordered by idle_days DESC (most stuck first).
    """
    ...

async def mark_stuck_alerted(self, goal_id: UUID) -> None:
    """Set last_stuck_alert_at = now() for a goal. Idempotent."""
    ...
```

### SQL implementation (`PostgresGoalStore`)

**`list_stuck` — ACTIVE case:**

```sql
SELECT
    g.*,
    MAX(m.completed_at) AS last_milestone_at,
    (
        SELECT title FROM goal_milestones
        WHERE goal_id = g.id
          AND status IN ('completed', 'skipped')
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    ) AS last_milestone_title
FROM goals g
LEFT JOIN goal_milestones m
    ON m.goal_id = g.id AND m.status IN ('completed', 'skipped')
WHERE g.status = 'active'
  AND (
      g.last_stuck_alert_at IS NULL
      OR g.last_stuck_alert_at < now() - ($2 || ' days')::interval
  )
GROUP BY g.id
HAVING
    (
        MAX(m.completed_at) IS NULL
        AND g.created_at < now() - ($1 || ' days')::interval
    )
    OR MAX(m.completed_at) < now() - ($1 || ' days')::interval
ORDER BY COALESCE(MAX(m.completed_at), g.created_at) ASC
```

**`list_stuck` — AWAITING_GATE case:**

```sql
SELECT
    g.*,
    vg.id          AS gate_id,
    vg.title       AS gate_title,
    vg.fired_at,
    vg.context_summary,
    vg.plan_summary,
    EXTRACT(DAY FROM now() - vg.fired_at)::int AS gate_idle_days,
    (
        SELECT title FROM goal_milestones
        WHERE goal_id = g.id
          AND status IN ('completed', 'skipped')
        ORDER BY completed_at DESC NULLS LAST
        LIMIT 1
    ) AS last_milestone_title
FROM goals g
JOIN verification_gates vg
    ON vg.goal_id = g.id AND vg.status = 'pending'
WHERE g.status = 'awaiting_gate'
  AND vg.fired_at < now() - ($1 || ' days')::interval
  AND (
      g.last_stuck_alert_at IS NULL
      OR g.last_stuck_alert_at < now() - ($2 || ' days')::interval
  )
ORDER BY vg.fired_at ASC
```

The implementation runs both queries and merges results into `list[StuckGoal]`, ordered
by `idle_days DESC`. Parameters: `$1 = idle_days`, `$2 = alert_cooldown_days`.

---

## Feature 3: Database Schema

```sql
-- migrations/0NN_stuck_goals.sql

ALTER TABLE goals ADD COLUMN last_stuck_alert_at TIMESTAMPTZ;

CREATE INDEX goals_last_stuck_alert_at_idx ON goals (last_stuck_alert_at);
```

No new table. The single nullable column on `goals` carries the cooldown signal.
The index supports the `last_stuck_alert_at < now() - interval` predicate efficiently.

---

## Feature 4: Weekly Job

### `StuckGoalJob`

```python
# ze/jobs/stuck_goals.py

from ze_core.proactive.job import proactive_job

@proactive_job
class StuckGoalJob:
    job_id = "stuck_goals"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        goal_store: GoalStore,
    ) -> None:
        self._notifier = notifier
        self._goal_store = goal_store

    async def run(self) -> None:
        stuck = await self._goal_store.list_stuck(
            idle_days=7,
            alert_cooldown_days=14,
        )
        if not stuck:
            log.info("stuck_goals_none")
            return

        log.info("stuck_goals_found", count=len(stuck))

        content, actions = _build_message(stuck)
        await self._notifier.push_notification(Notification(
            content=content,
            format="html",
            urgency="normal",
            actions=actions,
        ))

        for sg in stuck:
            await self._goal_store.mark_stuck_alerted(sg.goal.id)
```

The job has no LLM call. All message content is composed from DB state.

### Message composition

```python
def _build_message(stuck: list[StuckGoal]) -> tuple[str, list[Action]]:
    count = len(stuck)
    header = (
        f"One of your goals needs attention:"
        if count == 1
        else f"{count} of your goals need attention:"
    )

    sections: list[str] = [header]
    actions: list[Action] = []

    for i, sg in enumerate(stuck, start=1):
        goal_id_hex = sg.goal.id.hex   # 32-char, no hyphens
        num = f"#{i}" if count > 1 else ""

        if sg.kind == "awaiting_gate":
            body = (
                f"\n<b>{_html.escape(sg.goal.title)}</b>"
                f" — awaiting your approval for {sg.idle_days} days\n"
                f"Gate: <i>{_html.escape(sg.gate.title)}</i>"
            )
            row = i - 1
            actions += [
                Action(label=f"Approve {num}".strip(),
                       payload=f"goal_stuck:gate_approve:{goal_id_hex}", row=row),
                Action(label=f"Redirect {num}".strip(),
                       payload=f"goal_stuck:redirect:{goal_id_hex}", row=row),
                Action(label=f"Stop {num}".strip(),
                       payload=f"goal_stuck:gate_stop:{goal_id_hex}", row=row),
            ]
        else:
            last = (
                f"Last step: <i>{_html.escape(sg.last_milestone_title)}</i>"
                if sg.last_milestone_title
                else "No steps completed yet."
            )
            body = (
                f"\n<b>{_html.escape(sg.goal.title)}</b>"
                f" — no progress for {sg.idle_days} days\n"
                f"{last}"
            )
            row = i - 1
            actions += [
                Action(label=f"Redirect {num}".strip(),
                       payload=f"goal_stuck:redirect:{goal_id_hex}", row=row),
                Action(label=f"Pause {num}".strip(),
                       payload=f"goal_stuck:pause:{goal_id_hex}", row=row),
                Action(label=f"Abandon {num}".strip(),
                       payload=f"goal_stuck:abandon:{goal_id_hex}", row=row),
            ]

        sections.append(body)

    return "\n".join(sections), actions
```

Callback payloads use the full 32-char UUID hex (no hyphens) to avoid short-ID
collision handling. All payloads fit within Telegram's 64-byte callback data limit:

| Payload pattern | Max length |
|---|---|
| `goal_stuck:gate_approve:{32 hex}` | 56 bytes ✓ |
| `goal_stuck:gate_stop:{32 hex}` | 53 bytes ✓ |
| `goal_stuck:redirect:{32 hex}` | 51 bytes ✓ |
| `goal_stuck:pause:{32 hex}` | 48 bytes ✓ |
| `goal_stuck:abandon:{32 hex}` | 50 bytes ✓ |

---

## Feature 5: Telegram Callback Handler

### Dispatch

```python
# ze/telegram/bot.py

async def _handle_callback(self, callback: CallbackQuery) -> None:
    data = callback.data or ""
    if data.startswith("goal_stuck:"):
        await self._handle_stuck_callback(callback, data)
        return
    ...

async def _handle_stuck_callback(
    self,
    callback: CallbackQuery,
    data: str,
) -> None:
    parts = data.split(":", 2)
    if len(parts) != 3:
        await callback.answer()
        return

    _, action, goal_id_hex = parts
    try:
        goal_id = UUID(goal_id_hex)
    except ValueError:
        await callback.answer("Invalid goal reference.")
        return

    goal = await self._goal_store.get_goal(goal_id)
    if goal is None:
        await callback.answer("Goal not found.")
        return

    if action == "redirect":
        await self._stuck_redirect(callback, goal)
    elif action == "pause":
        await self._stuck_pause(callback, goal)
    elif action == "abandon":
        await self._stuck_abandon(callback, goal)
    elif action == "gate_approve":
        await self._stuck_gate_approve(callback, goal)
    elif action == "gate_stop":
        await self._stuck_gate_stop(callback, goal)
    else:
        await callback.answer()
```

### Action implementations

**Redirect:**
```python
async def _stuck_redirect(self, callback: CallbackQuery, goal: Goal) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Send me your instructions for <b>{html.escape(goal.title)}</b> "
        f"and I'll redirect it right away.",
        parse_mode="HTML",
    )
    # No ForceReply or explicit state — the user's next message naturally routes
    # to the goals agent via Phase 24's goal-aware routing context.
```

**Pause:**
```python
async def _stuck_pause(self, callback: CallbackQuery, goal: Goal) -> None:
    if goal.status not in (GoalStatus.ACTIVE, GoalStatus.AWAITING_GATE):
        await callback.answer("Already resolved.")
        return
    await self._goal_store.update_status(goal.id, GoalStatus.PAUSED)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Paused <b>{html.escape(goal.title)}</b>. "
        f"Resume it any time by telling me.",
        parse_mode="HTML",
    )
```

**Abandon:**
```python
async def _stuck_abandon(self, callback: CallbackQuery, goal: Goal) -> None:
    if goal.status in (GoalStatus.COMPLETED, GoalStatus.ABANDONED):
        await callback.answer("Already resolved.")
        return
    await self._goal_store.update_status(goal.id, GoalStatus.ABANDONED)
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Abandoned <b>{html.escape(goal.title)}</b>.",
        parse_mode="HTML",
    )
```

**Gate approve:**
```python
async def _stuck_gate_approve(self, callback: CallbackQuery, goal: Goal) -> None:
    gate = await self._goal_store.get_pending_gate(goal.id)
    if gate is None:
        await callback.answer("Gate already resolved.")
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await self._goal_executor.approve_gate(gate.id, user_feedback="Approved via stuck-goal alert.")
    await callback.message.answer(
        f"Approved — Ze will continue <b>{html.escape(goal.title)}</b>.",
        parse_mode="HTML",
    )
```

**Gate stop:**
```python
async def _stuck_gate_stop(self, callback: CallbackQuery, goal: Goal) -> None:
    gate = await self._goal_store.get_pending_gate(goal.id)
    if gate is None:
        await callback.answer("Gate already resolved.")
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await self._goal_executor.stop_gate(gate.id, user_feedback="Stopped via stuck-goal alert.")
    await callback.message.answer(
        f"Stopped <b>{html.escape(goal.title)}</b>.",
        parse_mode="HTML",
    )
```

Gate callbacks use the existing `GoalExecutor.approve_gate` / `stop_gate` methods introduced
in the goal engine. They trigger the same advance path as the original gate UX.

---

## Configuration

```yaml
# config/config.yaml
proactive:
  stuck_goals:
    enabled: true
    cron: "0 9 * * 2"   # Tuesday 09:00 — after the weekend, before the week fills up
```

Tuesday morning is chosen deliberately: after the weekend gives users natural downtime to
miss gate notifications, and early in the week gives them time to redirect before momentum
is lost.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_personal.goals.store.GoalStore` | **Extended** — `list_stuck()`, `mark_stuck_alerted()` |
| `ze_personal.goals.postgres.PostgresGoalStore` | Implements both new methods |
| `ze_personal.goals.types.Goal` | **Extended** — `last_stuck_alert_at` field |
| `ze_personal.goals.types.StuckGoal` | New type |
| `ze_core.proactive.notifier.ProactiveNotifier` | Push Telegram message |
| `ze_core.proactive.job.proactive_job` | Job decorator |
| `ze.telegram.bot.ZeBot` | `goal_stuck:*` callback handler |
| `ze_personal.goals.executor.GoalExecutor` | Gate resolution (`approve_gate`, `stop_gate`) |
| New migration | `ALTER TABLE goals ADD COLUMN last_stuck_alert_at TIMESTAMPTZ` |

---

## Implementation Notes

- **No LLM call** — the entire message is composed from structured DB data. `StuckGoal`
  carries everything needed: goal title, idle_days, last_milestone_title, gate title.
  This keeps the job cheap and instantaneous.

- **No advance() in the job** — the executor sweep (`goal_advance_sweep`, `*/15 * * * *`)
  already calls `advance()` for all ACTIVE goals every 15 minutes. By the time a goal
  has been idle for 7 days, any restart-caused stuckness would have self-healed hundreds
  of cycles ago. Calling `advance()` in the weekly job is redundant.

- **Full UUID hex in callbacks** — unlike the goal suggestion store (which uses 8-char
  short IDs to fit 64 bytes), stuck-goal callbacks use full 32-char UUID hex (no
  hyphens). This eliminates the need for short-ID collision handling and a
  `resolve_short_id`-style store method. All payloads fit within 64 bytes.

- **Keyboard removed on first resolution** — if two people somehow tap the same button
  (impossible for a single-user system, but defensive coding), the second callback hits
  the `goal.status not in (ACTIVE, AWAITING_GATE)` guard and answers silently. The
  keyboard is removed only after the write succeeds.

- **`mark_stuck_alerted` is called after push, not before** — if the push fails, the
  cooldown is not set. The next job run (7 days later) will try again. This is acceptable:
  a failed push is invisible to the user, so they should get another attempt.

- **Ordering** — stuck goals are ordered by idle_days DESC (most stuck first). This means
  the most overdue goal appears at the top of the consolidated message.

- **Redirect is informational, not stateful** — the redirect callback edits the keyboard
  away and sends a prompt. No ForceReply state is set. The next natural user message
  about the goal will be picked up by Phase 24's goal-aware routing, which injects active
  goal context into the embedding router. This avoids coupling stuck-goal callbacks to
  the active session store.

- **Gate stop semantics** — `stop_gate` resolves the gate as `GateStatus.STOPPED`. The
  executor's existing gate resolution path handles what happens next (typically pausing
  or abandoning the goal, depending on executor config). Phase 26 does not change that
  logic.

---

## Testing

| Test | Location |
|---|---|
| `list_stuck` returns ACTIVE goals with no milestone progress in window | `tests/goals/test_store.py` |
| `list_stuck` returns AWAITING_GATE goals with idle pending gate | `tests/goals/test_store.py` |
| `list_stuck` excludes goals alerted within cooldown window | `tests/goals/test_store.py` |
| `list_stuck` excludes PAUSED, COMPLETED, ABANDONED goals | `tests/goals/test_store.py` |
| `list_stuck` excludes new goals (created < idle_days ago) | `tests/goals/test_store.py` |
| `mark_stuck_alerted` sets `last_stuck_alert_at` | `tests/goals/test_store.py` |
| `StuckGoalJob.run` no-ops when no stuck goals | `tests/jobs/test_stuck_goals.py` |
| `StuckGoalJob.run` builds consolidated message for multiple stuck goals | `tests/jobs/test_stuck_goals.py` |
| `StuckGoalJob.run` calls `mark_stuck_alerted` for each goal after push | `tests/jobs/test_stuck_goals.py` |
| `StuckGoalJob.run` does not call `mark_stuck_alerted` if push fails | `tests/jobs/test_stuck_goals.py` |
| `_build_message` with one ACTIVE stuck goal omits goal number from button labels | `tests/jobs/test_stuck_goals.py` |
| `_build_message` with multiple goals includes #N label on each button | `tests/jobs/test_stuck_goals.py` |
| Pause callback updates status to PAUSED, removes keyboard | `tests/telegram/test_stuck_callbacks.py` |
| Pause callback no-ops if goal already resolved | `tests/telegram/test_stuck_callbacks.py` |
| Abandon callback updates status to ABANDONED, removes keyboard | `tests/telegram/test_stuck_callbacks.py` |
| Redirect callback removes keyboard and sends prompt, no state written | `tests/telegram/test_stuck_callbacks.py` |
| Gate approve callback calls `approve_gate`, removes keyboard | `tests/telegram/test_stuck_callbacks.py` |
| Gate approve callback no-ops if gate already resolved | `tests/telegram/test_stuck_callbacks.py` |
| Gate stop callback calls `stop_gate`, removes keyboard | `tests/telegram/test_stuck_callbacks.py` |
| Callback with invalid UUID hex answers with error | `tests/telegram/test_stuck_callbacks.py` |
| Callback for non-existent goal answers with error | `tests/telegram/test_stuck_callbacks.py` |

---

## Open Questions

- [x] **Consolidated vs per-goal messages** — one consolidated message with per-goal
  button rows. Keeps the alert as one Telegram item rather than flooding the chat.
- [x] **Staleness threshold** — 7 days.
- [x] **Alert cooldown** — 14 days per goal.
- [x] **"Keep going" button** — omitted. By the time the weekly job fires, the executor
  has retried hundreds of times. "Keep going" would be a no-op. Redirect / Pause / Abandon
  are the only meaningful actions.
- [x] **Auto-retry** — excluded. The 15-minute sweep already handles this continuously.
- [x] **Cross-goal conflict detection** — explicitly excluded; a different problem class.
  See `memory/project_goal_cross_awareness.md` for the richer future concept.
- [x] **Self-heal attempt in job** — excluded for the same reason as auto-retry.
- [x] **Schedule day/time** — Tuesday 09:00. After the weekend (when gate notifications
  are most likely missed), early enough in the week to take action.
