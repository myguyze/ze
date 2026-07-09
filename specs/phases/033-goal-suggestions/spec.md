# Proactive Goal Suggestions — Spec

> **Package:** `ze_personal` (planner, store, types), `ze` (job, Telegram callback)
> **Phase:** 25
> **Status:** Done
> **Depends on:** Phase 24 ([32-goal-collaboration.md](../032-goal-collaboration/spec.md)), Phase 23 ([31-goal-engine-v2.md](../031-goal-engine-v2/spec.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `GoalSuggestion` type + `SuggestionStatus` enum | ✅ Done |
| `GoalSuggestionStore` (DB-backed) | ✅ Done |
| Migration: `goal_suggestions` table | ✅ Done |
| `GoalPlanner.generate_suggestion()` with confidence gate | ✅ Done |
| `GoalSuggestionJob` (weekly cron) | ✅ Done |
| Telegram callback handler (`goal_suggest:*`) | ✅ Done |
| Accept flow → `GoalStore.save()` | ✅ Done |
| Dismiss flow | ✅ Done |
| "Tell me more" flow | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze holds rich signal about the user — memory facts, goal retrospectives, weekly narratives, episode
summaries — but today it only acts on goals the user explicitly creates. This phase gives Ze the
ability to synthesise that signal into a goal proposal and deliver it proactively via Telegram.

The key design constraint: Ze must not guess. Every suggestion must be grounded in a specific,
identifiable signal. If Ze cannot cite a concrete source, it does not fire. This constraint is what
separates a trusted advisor from a noisy recommendation engine.

This is the first time Ze initiates a message that isn't a status update or scheduled report. That
trust surface requires careful handling on first contact.

---

## Responsibilities

- On a weekly schedule, synthesise recent memory, goal retrospectives, and weekly narratives into
  a goal suggestion, if the signal is strong enough.
- Gate suggestion firing on a concrete, citable signal — return nothing if the bar is not met.
- Deliver the suggestion via Telegram with inline keyboard: accept, dismiss, or expand.
- On accept: create a properly structured goal in `GoalStore` identical to a user-created one.
- On dismiss: record the decision so Ze does not re-suggest within 30 days.
- On "tell me more": send an expanded rationale and re-offer the keyboard.
- Never send more than one suggestion per week. Never re-suggest the same topic within 30 days.

---

## Out of Scope

- **Cross-goal awareness** — detecting overlap or conflict between two concurrent goals.
  Requires a different reasoning pattern (across goal boundaries). Deferred.
- **Conversational goal creation** — multi-turn NL flow for goal refinement before acceptance.
  The current `create_goal` tool flow is sufficient for accepted suggestions.
- **Learning what the user rejects** — building a preference model from dismissed suggestions.
  Too little data in a single-user context; not worth the complexity.
- **Opt-in gate** — Ze does not ask permission before the first suggestion. It starts ambient,
  with a brief framing sentence on the very first message (see Feature 3).

---

## Module Location

```
packages/ze-core/
  ze_core/
    memory/
      store.py                ← extend MemoryStore protocol: list_recent_facts, list_recent_episodes
      postgres_store.py       ← implement new protocol methods

packages/ze-personal/
  ze_personal/
    goals/
      types.py                ← add GoalSuggestion, SuggestionStatus
      store.py                ← add save_retrospective(), list_recent_completed()
      suggestion_store.py     ← new: GoalSuggestionStore
      executor.py             ← _push_retrospective calls save_retrospective after synthesis
      planner.py              ← add generate_suggestion(), create_goal_from_suggestion()

packages/ze/
  ze/
    jobs/
      goal_suggestion.py      ← new: GoalSuggestionJob (@proactive_job)
    telegram/
      bot.py                  ← add goal_suggest:* callback handler
    migrations/
      0NN_goal_suggestions.sql ← ALTER goals + CREATE goal_suggestions
    config/
      config.yaml             ← add goal_suggestion schedule
```

---

## Feature 1: Data Types and Storage

### Types

```python
# ze_personal/goals/types.py

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

class SuggestionStatus(str, Enum):
    PENDING   = "pending"    # sent to user, awaiting response
    ACCEPTED  = "accepted"   # user accepted; goal created
    DISMISSED = "dismissed"  # user dismissed
    EXPIRED   = "expired"    # never resolved (e.g. Ze restarted before callback arrived)

@dataclass
class GoalSuggestion:
    id: UUID
    title: str
    objective: str
    rationale: str           # the specific citation: "Based on your retrospective for X…"
    source_type: str         # "retrospective" | "memory_facts" | "weekly_narrative"
    source_ref: str          # opaque ref to the signal (e.g. goal_id, fact cluster key)
    status: SuggestionStatus
    suggested_at: datetime
    resolved_at: datetime | None = None
    created_goal_id: UUID | None = None   # set on accept
```

### GoalSuggestionStore

```python
# ze_personal/goals/suggestion_store.py

class GoalSuggestionStore:
    def __init__(self, pool: asyncpg.Pool) -> None: ...

    async def save(self, suggestion: GoalSuggestion, week_key: str) -> bool:
        """
        Persist a new suggestion. Returns True on success, False if week_key already exists
        (unique violation → another job instance already saved this week's suggestion).
        Callers must treat False as a clean no-op, not an error.
        """
        ...

    async def get(self, suggestion_id: UUID) -> GoalSuggestion | None: ...

    async def mark_accepted(self, suggestion_id: UUID, goal_id: UUID) -> bool:
        """
        Atomically transitions status from PENDING → ACCEPTED.
        Issues: UPDATE ... WHERE id = $1 AND status = 'pending' RETURNING id
        Returns True if the row was updated, False if another callback already resolved it.
        Callers must treat False as a clean no-op (idempotent double-tap guard).
        """
        ...

    async def mark_dismissed(self, suggestion_id: UUID) -> bool:
        """Same atomic conditional pattern as mark_accepted. Returns False if already resolved."""
        ...

    async def mark_expired(self, suggestion_id: UUID) -> None:
        """Unconditional status update to EXPIRED. Used when push fails after save."""
        ...

    async def expire_stale_pending(self, older_than_days: int = 30) -> int:
        """
        Mark as EXPIRED any PENDING suggestions older than `older_than_days`.
        Returns the number of rows updated. Called at job start to prevent stale PENDING
        suggestions from blocking the weekly dedup window indefinitely.
        """
        ...

    async def was_suggested_recently(self, days: int = 30) -> bool:
        """
        Returns True if any suggestion with status PENDING, ACCEPTED, or DISMISSED
        was saved within the last `days` days. EXPIRED suggestions are excluded —
        they represent suggestions the user never saw and should not block future sends.
        """
        ...

    async def was_topic_suggested_recently(self, title: str, days: int = 30) -> bool:
        """Returns True if a suggestion with a similar title was sent recently.
        Uses case-insensitive substring match — not semantic similarity.
        Excludes EXPIRED suggestions."""
        ...

    async def resolve_short_id(self, short_id: str) -> GoalSuggestion | None:
        """
        Finds a suggestion whose UUID starts with `short_id` (8 hex chars).
        If multiple PENDING suggestions match (prefix collision), returns the most recent one.
        If multiple non-PENDING suggestions match and none are PENDING, returns the most recent.
        If the query returns > 1 PENDING suggestion (collision between two live keyboards),
        returns None — the callback handler will answer with an error.
        """
        ...
```

`was_topic_suggested_recently` guards against Ze restating the same idea in slightly different
words. The match is intentionally coarse: if the titles share 4+ consecutive words, treat as
duplicate. This is sufficient for the single-user context without needing embeddings.

### Database Schema

```sql
-- migrations/0NN_goal_suggestions.sql

-- Store retrospective text on the goal record so it is available as suggestion signal
-- without re-running LLM synthesis at job time.
ALTER TABLE goals ADD COLUMN retrospective_text TEXT;

CREATE TABLE goal_suggestions (
    id              UUID        PRIMARY KEY,
    title           TEXT        NOT NULL,
    objective       TEXT        NOT NULL,
    rationale       TEXT        NOT NULL,
    source_type     TEXT        NOT NULL,
    source_ref      TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',
    week_key        TEXT        UNIQUE,          -- ISO week 'YYYY-Www'; prevents double-send race
    suggested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    created_goal_id UUID        REFERENCES goals(id) ON DELETE SET NULL
);

CREATE INDEX goal_suggestions_suggested_at_idx ON goal_suggestions (suggested_at DESC);
```

`week_key` is set by the job to the ISO week string (e.g. `"2026-W23"`) at insert time. The
`UNIQUE` constraint makes a concurrent double-fire atomic: the second `INSERT` raises a unique
violation, the job catches it and exits cleanly. Only one suggestion can exist per calendar week
regardless of how many times the scheduler fires.

---

## Feature 2: Suggestion Generation with Confidence Gate

### GoalPlanner.generate_suggestion()

```python
# ze_personal/goals/planner.py

async def generate_suggestion(
    self,
    memory_facts: list[MemoryFact],
    episodes: list[Episode],
    retrospectives: list[GoalRetrospective],
    active_goal_titles: list[str],
) -> GoalSuggestion | None:
    """
    Synthesise signal into a goal suggestion. Returns None if signal is insufficient.

    Confidence gate: the LLM must identify a specific source before proposing anything.
    The prompt instructs the model to return a structured JSON with a `source_type`,
    `source_ref`, and `rationale` field. If rationale is generic (< 20 words, or contains
    no proper nouns or specific dates), the result is discarded and None is returned.

    Skips topics already covered by active_goal_titles (substring match, case-insensitive).
    """
    ...
```

### Prompt Design

```
You are analysing a user's memory, past goals, and retrospectives to identify one specific,
high-value goal they haven't yet set.

CONSTRAINTS:
- You must cite a concrete source: a specific retrospective, a cluster of related facts, or a
  repeated theme across multiple episodes. Vague observations ("the user seems interested in…")
  are not acceptable.
- The proposed goal must not duplicate any active goal listed below.
- If you cannot identify a clear, grounded opportunity, respond with {"suggestion": null}.

ACTIVE GOALS (do not duplicate):
{active_goal_titles}

RECENT SIGNAL:
Retrospectives (last 60 days):
{retrospectives}

Memory facts (last 90 days, highest-confidence):
{memory_facts}

Recent episodes (last 30 days):
{episodes}

Respond in JSON:
{
  "suggestion": {
    "title": "...",
    "objective": "...",         // 2-3 sentences, specific and actionable
    "rationale": "...",         // 1 sentence citing the exact source signal
    "source_type": "retrospective" | "memory_facts" | "weekly_narrative",
    "source_ref": "..."         // goal title for retrospectives; key phrase for facts/episodes
  } | null
}
```

### Confidence Gate (post-LLM)

After parsing the LLM response, apply these guards before accepting the suggestion:

| Check | Condition | Action |
|---|---|---|
| Null response | `suggestion == null` | Return `None` |
| Rationale too short | `len(rationale.split()) < 15` | Return `None` |
| Rationale generic | Rationale contains no specific title, date, or proper noun | Return `None` |
| Title duplicates active goal | Case-insensitive substring match against `active_goal_titles` | Return `None` |
| Objective too short | `len(objective.split()) < 10` | Return `None` |

These checks are cheap and prevent the most common LLM failure mode (plausible-sounding but
ungrounded output) from reaching the user.

---

## Feature 3: Weekly Suggestion Job

### GoalSuggestionJob

```python
# ze/jobs/goal_suggestion.py

from ze_core.proactive.job import proactive_job

@proactive_job
class GoalSuggestionJob:
    job_id = "goal_suggestion"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        goal_store: GoalStore,
        suggestion_store: GoalSuggestionStore,
        planner: GoalPlanner,
        memory_store: MemoryStore,
    ) -> None: ...

    async def run(self) -> None:
        # 0. Expire stale PENDING suggestions so they don't hold the dedup window forever
        expired = await self._suggestion_store.expire_stale_pending(older_than_days=30)
        if expired:
            log.info("goal_suggestion_expired_stale", count=expired)

        # 1. Dedup: skip if a live suggestion (non-EXPIRED) was sent in last 6 days
        if await self._suggestion_store.was_suggested_recently(days=6):
            log.info("goal_suggestion_skipped_recent")
            return

        # 2. Gather signal — treat any read failure as insufficient signal
        try:
            facts    = await self._memory_store.list_recent_facts(days=90, limit=40)
            episodes = await self._memory_store.list_recent_episodes(days=30, limit=10)
            retros   = await self._goal_store.list_retrospectives(days=60)
            active   = await self._goal_store.list_active_goal_titles()
        except Exception as exc:
            log.error("goal_suggestion_signal_read_failed", error=str(exc))
            return

        # 3. Generate — confidence gate is inside generate_suggestion(); JSON parse errors
        #    and OpenRouterErrors are caught there and returned as None
        suggestion = await self._planner.generate_suggestion(facts, episodes, retros, active)
        if suggestion is None:
            log.info("goal_suggestion_no_signal")
            return

        # 4. Persist (status=PENDING); week_key prevents concurrent double-save
        week_key = datetime.utcnow().strftime("%G-W%V")   # e.g. "2026-W23"
        saved = await self._suggestion_store.save(suggestion, week_key)
        if not saved:
            log.info("goal_suggestion_week_conflict")   # another instance already saved
            return

        # 5. Push Telegram message; on failure immediately expire the record so future
        #    job runs are not blocked by a suggestion the user never saw
        try:
            await self._push(suggestion)
        except Exception as exc:
            log.error("goal_suggestion_push_failed", error=str(exc))
            await self._suggestion_store.mark_expired(suggestion.id)
            return
```

### Telegram Message Format

```
[First suggestion only — no prior rows in goal_suggestions]
Here's a goal idea, based on what I've learned about you:

[All suggestions]
<b>{title}</b>
{objective}

<i>{rationale}</i>
```

Inline keyboard (2×1 layout):

```
[ Yes, create it ]  [ Dismiss ]
[ Tell me more   ]
```

Callback payloads (must fit 64-byte Telegram limit):
- `goal_suggest:accept:{suggestion_id_short}` — first 8 chars of UUID hex (28 bytes)
- `goal_suggest:dismiss:{suggestion_id_short}` — (29 bytes)
- `goal_suggest:more:{suggestion_id_short}` — (25 bytes)

The store resolves short IDs via `WHERE id::text LIKE '{short}%'`. UUIDs are random; 8-char prefix
collision probability across the expected suggestion volume (~52 per year) is negligible.

First-time detection: if `SELECT COUNT(*) FROM goal_suggestions` is 0 before saving, include the
intro sentence. No separate flag needed.

---

## Feature 4: Telegram Callback Handler

### ZeBot Changes

Add a `goal_suggest:*` callback route in the existing callback query dispatcher:

```python
# ze/telegram/bot.py

async def _handle_callback(self, callback: CallbackQuery) -> None:
    data = callback.data or ""

    if data.startswith("goal_suggest:"):
        await self._handle_suggestion_callback(callback, data)
        return
    ...

async def _handle_suggestion_callback(
    self,
    callback: CallbackQuery,
    data: str,
) -> None:
    _, action, short_id = data.split(":", 2)
    suggestion = await self._suggestion_store.resolve_short_id(short_id)

    if suggestion is None or suggestion.status != SuggestionStatus.PENDING:
        await callback.answer("This suggestion is no longer active.")
        return

    if action == "accept":
        await self._accept_suggestion(callback, suggestion)
    elif action == "dismiss":
        await self._dismiss_suggestion(callback, suggestion)
    elif action == "more":
        await self._expand_suggestion(callback, suggestion)
    else:
        await callback.answer()
```

### Accept Flow

```python
async def _accept_suggestion(
    self,
    callback: CallbackQuery,
    suggestion: GoalSuggestion,
) -> None:
    await callback.answer()

    try:
        goal = await self._planner.create_goal_from_suggestion(suggestion)
        await self._goal_store.save(goal)
        # Atomic conditional update — returns False if a concurrent callback already accepted
        accepted = await self._suggestion_store.mark_accepted(suggestion.id, goal.id)
        if not accepted:
            await callback.answer("Already accepted.", show_alert=False)
            return
        await callback.message.edit_reply_markup(reply_markup=None)   # remove keyboard on success
        await callback.message.answer(
            f"Done — <b>{html.escape(goal.title)}</b> is now an active goal. "
            f"Ze will begin planning milestones shortly.",
            parse_mode="HTML",
        )
        task = asyncio.create_task(self._executor.advance(goal.id))
        task.add_done_callback(
            lambda t: log.error("goal_suggestion_advance_failed", error=str(t.exception()))
            if t.exception() else None
        )
    except Exception as exc:
        log.error("goal_suggestion_accept_failed", error=str(exc))
        # Keyboard intentionally left intact so the user can tap again
        await callback.message.answer(
            "Something went wrong creating the goal — the option above is still available."
        )
```

`create_goal_from_suggestion` is a thin `GoalPlanner` method that maps `GoalSuggestion` fields
into a `Goal` dataclass with `status=ACTIVE` and no milestones yet (executor will plan them).

The keyboard is removed only after all writes succeed. If any step fails, the keyboard remains
so the user can retry without having to recreate the goal manually.

### Dismiss Flow

```python
async def _dismiss_suggestion(
    self,
    callback: CallbackQuery,
    suggestion: GoalSuggestion,
) -> None:
    dismissed = await self._suggestion_store.mark_dismissed(suggestion.id)
    if not dismissed:
        await callback.answer("Already resolved.", show_alert=False)
        return
    await callback.answer("Dismissed.")
    await callback.message.edit_reply_markup(reply_markup=None)
```

No confirmation step — dismiss is low-stakes and reversible by asking Ze to create the goal
manually. The atomic `mark_dismissed` call happens before removing the keyboard; if it returns
False (concurrent accept won the race), the dismiss is silently dropped.

### "Tell Me More" Flow

```python
async def _expand_suggestion(
    self,
    callback: CallbackQuery,
    suggestion: GoalSuggestion,
) -> None:
    await callback.answer()
    # Send an expanded message (no LLM call — use stored rationale + objective)
    text = (
        f"Here's more context on why I suggested <b>{html.escape(suggestion.title)}</b>:\n\n"
        f"{html.escape(suggestion.rationale)}\n\n"
        f"The goal would be: {html.escape(suggestion.objective)}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Yes, create it",
                                 callback_data=f"goal_suggest:accept:{short_id}"),
            InlineKeyboardButton(text="Dismiss",
                                 callback_data=f"goal_suggest:dismiss:{short_id}"),
        ],
    ])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
```

"Tell me more" does not consume an LLM call — it only expands the stored `rationale` and
`objective`. This keeps the interaction instant and avoids a second LLM round-trip for a UI
gesture.

---

## Interface Contract

### `GoalPlanner.generate_suggestion(facts, episodes, retrospectives, active_goal_titles) -> GoalSuggestion | None`

One LLM completion. Returns `None` in all of the following cases — never raises to the job:
- Confidence gate rejects the output
- LLM returns `{"suggestion": null}`
- LLM response is not valid JSON (`json.JSONDecodeError` caught internally)
- LLM response is valid JSON but missing required fields (`KeyError` / `TypeError` caught internally)
- `OpenRouterError` or network timeout (caught internally, logged as `goal_suggestion_llm_failed`)

The job treats `None` as a clean no-op in all cases.

### `GoalPlanner.create_goal_from_suggestion(suggestion: GoalSuggestion) -> Goal`

Pure mapping — no LLM call. Maps suggestion fields into a `Goal` with `status=ACTIVE`,
`milestones=[]`, `created_at=now()`. Executor will plan milestones on first `advance()`.

### `GoalSuggestionStore.was_suggested_recently(days) -> bool`

Single `COUNT` query. Used by the job for dedup. Safe to call frequently.

### Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| `generate_suggestion` LLM call fails | Caught inside `generate_suggestion`, returns `None`; job logs and exits cleanly |
| `generate_suggestion` returns malformed JSON | Caught inside `generate_suggestion` (`JSONDecodeError`), returns `None` |
| Confidence gate rejects LLM output | `generate_suggestion` returns `None`; job logs `goal_suggestion_no_signal` and exits |
| Signal DB reads fail (`MemoryStore`, `GoalStore`) | Job catches in step 2, logs `goal_suggestion_signal_read_failed`, exits — no suggestion sent |
| Two cron firings race before either saves | `week_key UNIQUE` constraint rejects the second `INSERT`; `save()` returns `False`; second job exits logging `goal_suggestion_week_conflict` |
| Push fails after save | Job catches, calls `mark_expired(suggestion.id)`, exits — dedup window cleared; next week's job can fire normally |
| Suggestion sent, user never responds for 30 days | `expire_stale_pending(30)` marks it `EXPIRED` on next job run; `was_suggested_recently` excludes `EXPIRED`; dedup window resets |
| User double-taps Accept | First callback: `mark_accepted` returns `True`, goal created. Second callback: `mark_accepted` returns `False` (WHERE status='pending' matches nothing); answered silently |
| User taps Accept and Dismiss simultaneously | Whichever callback's `mark_accepted`/`mark_dismissed` UPDATE runs first wins; the other gets `False` and is dropped |
| User accepts, any write step fails | Exception caught; keyboard left intact on original message; user sees error and can tap again |
| `executor.advance()` task raises | `add_done_callback` logs the exception; goal exists in `GoalStore` with `ACTIVE` status and no milestones. The executor's scheduler sweep will re-attempt `advance()` on the next cycle |
| Callback for already-resolved suggestion | `suggestion.status != PENDING` check at handler entry; `callback.answer("This suggestion is no longer active.")` |
| Callback after Ze restart | `GoalSuggestionStore` is DB-backed; suggestion record persists; all callback paths resolve correctly |
| `resolve_short_id` returns multiple PENDING rows (prefix collision) | Returns `None`; handler answers "something went wrong" — user can dismiss and ask Ze to create the goal manually. Collision probability across ~52 suggestions/year is negligible; this path is a safety net, not an expected case |
| Active goals cover all obvious opportunities | `active_goal_titles` dedup + confidence gate returns `None`; job is a no-op |
| User has < 2 weeks of memory / no retrospectives | Insufficient signal → `None`; job is a no-op. Feature naturally delays until Ze knows enough |

---

## Configuration

```yaml
# config/config.yaml
proactive:
  goal_suggestion:
    schedule: "0 19 * * 0"   # Sunday 19:00 (one hour after goal_narrative)
```

Running goal_suggestion one hour after goal_narrative ensures the weekly narrative has fired first,
so it is available as signal for the suggestion generator.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.memory.store.MemoryStore` | **Extended** — add `list_recent_facts(days, limit)` and `list_recent_episodes(days, limit)` to protocol + `PostgresMemoryStore` |
| `ze_personal.goals.store.GoalStore` | **Extended** — add `save_retrospective(goal_id, text)` and `list_recent_completed(since)` |
| `ze_personal.goals.executor.GoalExecutor` | **Modified** — `_push_retrospective` must call `save_retrospective` after synthesis |
| `ze_personal.goals.planner.GoalPlanner` | `generate_suggestion`, `create_goal_from_suggestion` |
| `ze_personal.goals.suggestion_store.GoalSuggestionStore` | New — persist suggestions, dedup, status updates |
| `ze_core.proactive.notifier.ProactiveNotifier` | Push Telegram message |
| `ze_core.proactive.job.proactive_job` | Job decorator |
| `ze.telegram.bot.ZeBot` | `goal_suggest:*` callback handler |
| `ze_core.container.Container` | Register `GoalSuggestionJob`, `GoalSuggestionStore` |
| New migration | `ALTER TABLE goals ADD COLUMN retrospective_text`, new `goal_suggestions` table |

---

## Implementation Notes

- **No PushLogStore**: `GoalSuggestionJob` manages dedup via `GoalSuggestionStore` directly.
  The suggestions table is the authoritative record — no separate push log entry needed.
- **`week_key` as atomic double-fire guard**: The `UNIQUE` constraint on `week_key` makes
  concurrent job instances safe without advisory locks. `save()` uses `INSERT ... ON CONFLICT
  (week_key) DO NOTHING RETURNING id`; a return of zero rows means another instance won. This
  is simpler than application-level locking and survives Ze restarts between the two firings.
- **EXPIRED status breaks the dedup loop**: `was_suggested_recently` excludes `EXPIRED`.
  Without this, a suggestion that was saved but never delivered (push failed) or never seen
  (user ignored for 30 days and it was expired) would block future sends indefinitely. EXPIRED
  rows are kept in the table for audit and to power `was_topic_suggested_recently` (we don't
  want to re-suggest the same topic even if the original delivery failed).
- **Keyboard removed only on success**: The accept flow removes the inline keyboard only after
  all writes succeed. If any step fails, the keyboard remains intact on the original message so
  the user can tap again without recreating the goal manually.
- **Atomic accept/dismiss via conditional UPDATE**: `mark_accepted` and `mark_dismissed` use
  `UPDATE ... WHERE status = 'pending' RETURNING id`. If 0 rows are returned, a concurrent
  callback already resolved the suggestion. The losing callback is silently dropped — no error
  is surfaced to the user.
- **`executor.advance()` exception visibility**: `asyncio.create_task()` swallows exceptions
  by default. The `add_done_callback` pattern on the task logs the error explicitly. The
  executor's scheduler sweep (`GoalExecutor._sweep`) will re-attempt `advance()` for any
  `ACTIVE` goal with no `IN_PROGRESS` milestone, so a failed first advance self-heals on the
  next sweep cycle. The goal will not be stuck permanently.
- **Short ID resolution**: Callback payloads use 8-char UUID prefixes (28–29 bytes). On the
  rare collision, `resolve_short_id` returns `None` and the user sees "something went wrong."
  Collision probability across ~52 suggestions/year is negligible in practice.
- **No LLM in "tell me more"**: The expanded message uses stored `rationale` and `objective`.
  Instant response, zero extra cost. A `GoalPlanner.expand_suggestion()` method can be added
  later without changing the callback contract if richer expansion is wanted.
- **Executor starts on accept**: `create_goal_from_suggestion` creates a goal with no milestones.
  The executor's first `advance()` triggers milestone planning via `GoalPlanner.plan()`.
  Identical to the user-created goal flow — no special path for suggested goals.
- **Signal window**: Facts (90 days), episodes (30 days), retrospectives (60 days). Retrospectives
  get the widest window because they are rare and information-dense. All three windows are
  intentionally generous to ensure the feature fires at least occasionally during early use.
- **Sunday 19:00 after narrative**: The goal narrative job runs at 18:00 Sunday. Running suggestion
  at 19:00 ensures the weekly narrative is committed before the suggestion generator reads signal.

---

## Testing

| Test | Location |
|---|---|
| `generate_suggestion` returns `None` when no signal | `tests/goals/test_planner.py` |
| `generate_suggestion` returns `None` when confidence gate rejects rationale | `tests/goals/test_planner.py` |
| `generate_suggestion` returns `None` on malformed JSON from LLM | `tests/goals/test_planner.py` |
| `generate_suggestion` returns `None` on `OpenRouterError` | `tests/goals/test_planner.py` |
| `generate_suggestion` skips topic matching active goal title | `tests/goals/test_planner.py` |
| `generate_suggestion` returns `GoalSuggestion` on valid LLM output | `tests/goals/test_planner.py` |
| `GoalSuggestionJob.run` expires stale PENDING suggestions before dedup check | `tests/jobs/test_goal_suggestion.py` |
| `GoalSuggestionJob.run` skips when `was_suggested_recently` is True | `tests/jobs/test_goal_suggestion.py` |
| `GoalSuggestionJob.run` exits cleanly when signal DB read raises | `tests/jobs/test_goal_suggestion.py` |
| `GoalSuggestionJob.run` exits when `save()` returns False (week conflict) | `tests/jobs/test_goal_suggestion.py` |
| `GoalSuggestionJob.run` calls `mark_expired` when push fails after save | `tests/jobs/test_goal_suggestion.py` |
| `GoalSuggestionJob.run` skips when `generate_suggestion` returns None | `tests/jobs/test_goal_suggestion.py` |
| `GoalSuggestionJob.run` saves suggestion and pushes notification | `tests/jobs/test_goal_suggestion.py` |
| First suggestion includes intro sentence | `tests/jobs/test_goal_suggestion.py` |
| Accept callback creates goal, removes keyboard only on success | `tests/telegram/test_suggestion_callbacks.py` |
| Accept callback leaves keyboard intact when goal creation fails | `tests/telegram/test_suggestion_callbacks.py` |
| Accept callback is idempotent on double-tap (second call returns False from store) | `tests/telegram/test_suggestion_callbacks.py` |
| Accept callback on already-resolved suggestion is answered silently | `tests/telegram/test_suggestion_callbacks.py` |
| Dismiss callback uses atomic conditional update | `tests/telegram/test_suggestion_callbacks.py` |
| Dismiss callback is a no-op if accept already won the race | `tests/telegram/test_suggestion_callbacks.py` |
| "Tell me more" sends expanded message with keyboard, no LLM call | `tests/telegram/test_suggestion_callbacks.py` |
| `was_suggested_recently` returns True for PENDING within window | `tests/goals/test_suggestion_store.py` |
| `was_suggested_recently` excludes EXPIRED suggestions | `tests/goals/test_suggestion_store.py` |
| `was_suggested_recently` returns False outside window | `tests/goals/test_suggestion_store.py` |
| `expire_stale_pending` marks old PENDING suggestions EXPIRED, returns count | `tests/goals/test_suggestion_store.py` |
| `expire_stale_pending` does not affect ACCEPTED or DISMISSED suggestions | `tests/goals/test_suggestion_store.py` |
| `save()` returns False on duplicate `week_key` | `tests/goals/test_suggestion_store.py` |
| `mark_accepted` returns True on first call, False on second (atomic) | `tests/goals/test_suggestion_store.py` |
| `mark_dismissed` returns False when suggestion already ACCEPTED | `tests/goals/test_suggestion_store.py` |
| `resolve_short_id` finds suggestion by 8-char prefix | `tests/goals/test_suggestion_store.py` |
| `resolve_short_id` returns None when multiple PENDING suggestions share prefix | `tests/goals/test_suggestion_store.py` |
| `create_goal_from_suggestion` maps suggestion fields correctly | `tests/goals/test_planner.py` |
| `GoalStore.save_retrospective` persists text to `retrospective_text` column | `tests/goals/test_store.py` |
| `GoalStore.list_recent_completed` returns only completed goals within window | `tests/goals/test_store.py` |
| `GoalExecutor._push_retrospective` calls `save_retrospective` after synthesis | `tests/goals/test_executor.py` |
| `GoalExecutor._push_retrospective` still pushes notification when `save_retrospective` fails | `tests/goals/test_executor.py` |
| `MemoryStore.list_recent_facts` returns facts within time window, respects limit | `tests/memory/test_postgres_store.py` |
| `MemoryStore.list_recent_episodes` returns episodes within time window, respects limit | `tests/memory/test_postgres_store.py` |

---

## Open Questions

- [x] **Trigger**: weekly cron only (not post-retrospective hook). Simpler, predictable. → **Weekly cron, Sunday 19:00.**
- [x] **Trust framing**: ambient start. Ze includes one intro sentence on the first suggestion only. No opt-in gate. → **Ambient.**
- [x] **`list_retrospectives` API**: `GoalStore` has no such method, and retrospective text is currently synthesised then pushed to Telegram but never persisted. → **Store retrospective text on the goal record.** Add `retrospective_text TEXT` column to the `goals` table (included in the Phase 25 migration below). When `GoalExecutor._push_retrospective()` calls `synthesize_retrospective()`, it must also call a new `GoalStore.save_retrospective(goal_id, text)` method. Add `GoalStore.list_recent_completed(since: datetime) -> list[Goal]` for the job to query. The suggestion generator reads `goal.retrospective_text` directly — no LLM call in the job for this step.
- [x] **`MemoryStore.list_recent_facts` / `list_recent_episodes`**: The `MemoryStore` protocol only exposes `get_context()` (semantic retrieval for agent execution), `write_episode()`, `propose_facts()`, `get_profile()`. Batch time-windowed reads do not exist. → **Extend the `MemoryStore` protocol** with two new methods: `list_recent_facts(days: int, limit: int) -> list[UserFact]` and `list_recent_episodes(days: int, limit: int) -> list[Episode]`. Both are direct time-windowed DB queries on `user_facts` and `memory_episodes` respectively. `PostgresMemoryStore` implements them. The protocol lives in `ze_core`; the implementation in `ze_core/memory/postgres_store.py`.
- [ ] **Signal quality threshold**: The confidence gate rules (rationale ≥ 15 words, contains proper noun/date) are heuristic. Validate against a sample of real memory data before finalising the prompt.
