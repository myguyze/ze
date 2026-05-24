# Spec 22 — Reminders Agent

## Implementation Status

| Feature | Status |
|---------|--------|
| `user_reminders` DB table + migration | ✅ Done |
| `ReminderStore` — CRUD + fire | ✅ Done |
| `RemindersAgent` — set / list / cancel via NL | ✅ Done |
| APScheduler wiring — fire at scheduled time | ✅ Done |
| Startup replay of unfired reminders | ✅ Done |
| Progress message (`reminders.thinking`) | ✅ Done |
| Container wiring + config | ✅ Done |
| Tests | ✅ Done |

## Problem

Ze can set calendar events and proactive workflow alerts, but has no way to handle
simple time-based user reminders ("remind me in 2 hours", "remind me tomorrow at 9am
to call João"). These don't belong on a calendar; they're lightweight one-off pushes.

---

## Scope

- Set a reminder from natural language
- List pending reminders
- Cancel a pending reminder
- Fire the reminder via `ProactiveNotifier.push` at the scheduled time
- Survive app restarts (unsent reminders replayed from DB at startup)

Out of scope: recurring reminders (use workflows), snooze, multi-user.

---

## Data

### New table: `user_reminders`

```sql
CREATE TABLE user_reminders (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label      TEXT NOT NULL,
    fire_at    TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent       BOOLEAN NOT NULL DEFAULT false,
    sent_at    TIMESTAMPTZ
)
```

Index on `(fire_at) WHERE sent = false` for efficient unsent lookups.

Separate from `calendar_reminders` (which is tied to Google Calendar event IDs).

---

## Architecture

```
RemindersAgent.run()
  └─ Haiku: NL → {action, label, fire_at}
       ├─ set    → ReminderStore.create() + WorkflowScheduler.schedule_at()
       ├─ list   → ReminderStore.list_pending()
       └─ cancel → ReminderStore.delete() + WorkflowScheduler.remove_job_if_exists()

fire_at fires → fire_reminder(store, notifier, id) → ProactiveNotifier.push()
```

### `ze/reminders/store.py` — `ReminderStore`

Pure DB wrapper. No LLM, no scheduler knowledge.

- `create(label, fire_at) -> UUID`
- `list_pending() -> list[Reminder]`
- `get(id) -> Reminder | None`
- `delete(id) -> None`
- `mark_sent(id) -> None`

### `ze/reminders/store.py` — `fire_reminder(store, notifier, id)`

Standalone async function. Used by both the agent (for newly created reminders)
and the container (for startup replay). Idempotent — checks `sent` before pushing.

### `ze/agents/reminders/agent.py` — `RemindersAgent`

Registered as `"reminders"`. Dependencies (resolved by type via bootstrap DI):
`OpenRouterClient`, `ReminderStore`, `WorkflowScheduler`, `ProactiveNotifier`, `Settings`.

System prompt includes current UTC time and user timezone so Haiku can resolve
relative references ("tomorrow", "in 2 hours").

### Startup replay — `ze/container.py`

After creating `ReminderStore`, fetch all unsent reminders and re-schedule them:

```python
pending = await reminder_store.list_pending()
for r in pending:
    workflow_scheduler.schedule_at(
        fn=lambda rid=r.id: fire_reminder(reminder_store, notifier, rid),
        dt=r.fire_at,
        job_id=f"user_reminder:{r.id}",
    )
```

---

## Agent behaviour

### Set

User: "Remind me in 2 hours to take my medication"

```
⏰ Reminder set: Take medication
I'll remind you in 2 hours (Fri 22 May at 13:00 UTC)
```

Past-time requests are rejected: "That time is already in the past."

### List

User: "What reminders do I have?"

```
⏰ Pending reminders (2):
  1. Take medication — Fri 22 May at 13:00 UTC
  2. Call João — Sat 23 May at 09:00 UTC
```

No pending reminders → "You have no pending reminders."

### Cancel

User: "Cancel my reminder about medication"

```
✅ Reminder cancelled: Take medication
```

No match → lists pending and asks the user to be more specific.

---

## Config

```yaml
reminders:
  enabled: true
  description: |
    Sets, lists, and cancels one-off time-based reminders. Use when the user asks
    to be reminded about something at a specific time or after a delay.
  model: anthropic/claude-haiku-4-5
  tools: []
  timeout_seconds: 15
  intent_map:
    manage: ""
  capabilities:
    manage: autonomous
```

---

## Progress message key

`reminders.thinking` → "⏰ Setting that reminder..." / "🔔 On it..."
