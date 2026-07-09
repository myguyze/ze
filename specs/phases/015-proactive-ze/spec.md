# Proactive Ze — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| Migration 006 — `push_log` + `calendar_reminders` tables | ✅ Done |
| `ProactiveNotifier` | ✅ Done |
| Config `proactive:` section | ✅ Done |
| `MorningBriefing` — stats-only, scheduled | ✅ Done |
| Unreviewed-facts nudge (part of morning briefing) | ✅ Done |
| Workflow failure alerts (immediate) | ✅ Done |
| `CalendarReminderScheduler` + daily sync job | ✅ Done |
| `WorkflowScheduler.schedule_at()` — one-shot DateTrigger | ✅ Done |
| Startup reminder replay | ✅ Done |
| Calendar reminder confirmation push | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze currently speaks only when spoken to. This phase adds three proactive push
behaviours delivered over the existing Telegram bot channel:

1. **Morning briefing** — a daily stats summary (unreviewed facts, upcoming
   workflows, recent failures). If the unreviewed-facts count exceeds the
   configured threshold, the briefing acts as the nudge.

2. **Workflow failure alerts** — an immediate push the moment a scheduled
   workflow run fails.

3. **Calendar reminders** — event-aware, interval-assessed reminders scheduled
   by a daily calendar sync job.

---

## Out of Scope

- LLM-composed briefing text — the briefing is templated, no LLM call.
- User commands to adjust reminder intervals (users can ask Ze conversationally,
  handled by the existing calendar agent in a future turn).
- Multi-user push (single-user system, always pushes to `settings.telegram_allowed_chat_id`).
- Push rate limiting beyond the per-event-type cooldown in `push_log`.
- Inline keyboard buttons on any proactive message (push-only, no confirmation flow).

---

## Repository Layout

```
ze/
├── proactive/
│   ├── __init__.py
│   ├── notifier.py          # ProactiveNotifier
│   ├── briefing.py          # MorningBriefing
│   └── reminders.py         # CalendarReminderScheduler
├── workflow/
│   └── scheduler.py         # add schedule_at() method
├── container.py             # wire ProactiveNotifier, MorningBriefing, CalendarReminderScheduler
└── migrations/versions/
    └── 006_proactive.py
```

Config:
```
config/config.yaml           # add proactive: section
```

Tests:
```
tests/proactive/
    __init__.py
    test_notifier.py
    test_briefing.py
    test_reminders.py
```

---

## Push Infrastructure

### `ProactiveNotifier` (`ze/proactive/notifier.py`)

Thin wrapper around `aiogram.Bot` and `chat_id`. The single push path for all
proactive messages.

```python
class ProactiveNotifier:
    def __init__(self, bot: Bot, chat_id: int) -> None: ...

    async def push(self, text: str) -> None:
        """Send text to the user. Swallows and logs errors — never raises."""
```

`chat_id` is always `int(settings.telegram_allowed_chat_id)`.

The notifier does not format text — callers provide final strings. Long messages
are split at `\n` boundaries to respect the 4096-character Telegram limit (same
`_split` logic as `ZeBot`).

### `push_log` table

Deduplication and audit log for all proactive pushes. Schema in Migration 006.

Dedup query:
```sql
SELECT 1 FROM push_log
WHERE event_type = $1
  AND sent_at > NOW() - INTERVAL '$2 hours'
LIMIT 1
```

Callers check this before pushing; if a row is found, the push is skipped. After
pushing, a row is inserted.

`event_type` values:

| Value | Cooldown |
|-------|----------|
| `morning_brief` | 20 hours (prevents double-fire if cron drifts) |
| `workflow_failure:<workflow_id>` | configurable `workflow_failure_cooldown_hours` |
| `calendar_reminder:<reminder_id>` | no cooldown — each reminder ID is unique |

---

## Morning Briefing

### `MorningBriefing` (`ze/proactive/briefing.py`)

```python
class MorningBriefing:
    def __init__(
        self,
        notifier: ProactiveNotifier,
        pool: asyncpg.Pool,
        settings: Settings,
    ) -> None: ...

    async def run(self) -> None: ...
```

`run()` is the APScheduler job target.

### Logic

1. **Dedup check** — query `push_log` for `morning_brief` within 20 hours. Skip if found.
2. **Load stats** — three DB queries:
   - `SELECT COUNT(*) FROM user_facts WHERE reviewed = false AND contradicted = false`
   - `SELECT name, schedule, last_run_at FROM workflows WHERE enabled = true AND schedule IS NOT NULL ORDER BY name`
   - `SELECT workflow_name, failed_at FROM push_log WHERE event_type LIKE 'workflow_failure:%' AND sent_at > NOW() - INTERVAL '24 hours'`
     *(workflow failures pushed in the last 24 hours)*
3. **Compose message** — template:

```
Good morning! Here's your Ze briefing.

📋 Unreviewed facts: {N}   (tap "Manage memory" or ask Ze to review)
⚙️  Scheduled workflows: {names or "none"}
```

If any workflow failures were alerted in the last 24 hours, append:
```
⚠️  Recent failures: {workflow_name} at {time}
```

If `unreviewed_count >= unreviewed_nudge_threshold`, append:
```
💡 You have {N} facts waiting for review.
```

No LLM call. The briefing is always produced from the template.

4. **Push** via `notifier.push()`.
5. **Write** a `push_log` row: `event_type = 'morning_brief'`.

### Schedule

Registered in `container.py` via `workflow_scheduler.schedule_job()`:

```python
workflow_scheduler.schedule_job(
    fn=morning_briefing.run,
    cron=settings.proactive_config.get("briefing_cron", "0 8 * * *"),
    job_id="morning_briefing",
)
```

Gated on `settings.proactive_config.get("briefing_enabled", True)`.

---

## Workflow Failure Alerts

### `WorkflowScheduler` changes

`WorkflowScheduler.__init__` gains an optional parameter:

```python
def __init__(
    self,
    ...,
    notifier: ProactiveNotifier | None = None,
) -> None:
```

In `_run_workflow`, the existing exception handler becomes:

```python
except Exception as exc:
    log.exception("workflow_execution_error", workflow=workflow.name, error=str(exc))
    await self._store.finish_execution(execution_id, "failed", error=str(exc))
    if self._notifier:
        await self._push_failure_alert(workflow, exc)
    return
```

```python
async def _push_failure_alert(self, workflow: Workflow, exc: Exception) -> None:
    cfg = self._settings.proactive_config
    if not cfg.get("workflow_failure_alerts", True):
        return
    cooldown = int(cfg.get("workflow_failure_cooldown_hours", 1))
    event_type = f"workflow_failure:{workflow.id}"
    async with self._pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT 1 FROM push_log WHERE event_type = $1 AND sent_at > NOW() - INTERVAL '$2 hours'",
            event_type, str(cooldown),
        )
        if existing:
            return
    await self._notifier.push(
        f"⚠️ Workflow failed: *{workflow.name}*\n`{str(exc)[:200]}`"
    )
    async with self._pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO push_log (event_type, payload) VALUES ($1, $2)",
            event_type, str(exc)[:500],
        )
```

`WorkflowScheduler` is constructed without `pool` today — it needs `pool` added
to support the dedup query. Wire it in `container.py`.

---

## Calendar Reminders

### Overview

A daily sync job fetches calendar events for the next 7 days. For each event
not yet seen by Ze (no row in `calendar_reminders`), it:

1. Calls Haiku to assess appropriate reminder intervals.
2. Inserts `calendar_reminders` rows for each interval.
3. Schedules a one-shot APScheduler `DateTrigger` job per reminder.
4. Pushes a confirmation message: "I've scheduled N reminders for [event]."

On app startup, unsent future reminders are reloaded from DB and rescheduled.

Calendar reminders are only active when `GoogleCredentials` is available (i.e.,
the three Google OAuth env vars are set and `GoogleCredentials.from_settings()`
returns a non-None object). The calendar agent's `enabled` flag in config
controls routing only — it has no effect here.

### `CalendarReminderScheduler` (`ze/proactive/reminders.py`)

```python
class CalendarReminderScheduler:
    def __init__(
        self,
        notifier: ProactiveNotifier,
        pool: asyncpg.Pool,
        openrouter_client: OpenRouterClient,
        workflow_scheduler: WorkflowScheduler,
        google_credentials: GoogleCredentials | None,   # None → sync() is a no-op
        settings: Settings,
    ) -> None: ...

    async def start(self) -> None:
        """Reload unsent future reminders from DB and reschedule. Called at startup."""

    async def sync(self) -> None:
        """Daily sync job: fetch events, assess new ones, schedule reminders."""

    async def fire_reminder(self, reminder_id: UUID) -> None:
        """One-shot job target: push the reminder and mark it sent."""
```

### `WorkflowScheduler.schedule_at()` — new method

APScheduler supports one-shot jobs via `DateTrigger`. Add:

```python
def schedule_at(self, fn, dt: datetime, job_id: str) -> None:
    from apscheduler.triggers.date import DateTrigger
    self._scheduler.add_job(
        fn,
        trigger=DateTrigger(run_date=dt),
        id=job_id,
        replace_existing=True,
        max_instances=1,
    )

def remove_job_if_exists(self, job_id: str) -> None:
    if self._scheduler.get_job(job_id):
        self._scheduler.remove_job(job_id)
```

### Daily sync job

`CalendarReminderScheduler.sync()` logic:

1. Check `self._credentials is None` — return immediately if so.
2. Fetch events for the next 7 days: `credentials.calendar().events().list(...)`
   with `timeMin = now`, `timeMax = now + 7 days`, `singleEvents = True`,
   `orderBy = "startTime"`. Same call pattern as the `list_events` tool.
3. For each event:
   a. Check `calendar_reminders WHERE event_id = $1` — skip if rows exist
      (already assessed this event).
   b. Call `_assess_intervals(event)` → list of `datetime` objects.
   c. Insert rows into `calendar_reminders`.
   d. Schedule one-shot APScheduler jobs.
   e. Push confirmation message.
4. Check for rescheduled events: if an event's `start_time` has changed, delete
   its unsent reminders, re-assess, re-schedule, and push an update notification.

Rescheduled-event detection: compare `event.updated_at` against
`calendar_reminders.assessed_at` for the same `event_id`.

### Interval assessment prompt (Haiku)

**System:**
```
You are Ze's calendar assistant. Given a calendar event, return a JSON object
with a single key "intervals" — an array of strings representing reminder
offsets before the event start time. Choose intervals that would help a person
prepare appropriately. Use values like "2 weeks", "3 days", "2 hours",
"30 minutes". Return only the JSON object. Do not explain.
```

**User:**
```
Event: {title}
Duration: {duration_minutes} minutes
Description: {description or "(none)"}
```

**Response parsing:** parse `intervals` list, convert each string to a `timedelta`,
compute `fire_at = event_start - offset`. Discard any `fire_at` in the past or
less than 10 minutes in the future. If Haiku fails or returns malformed JSON,
fall back to `["1 hour"]`.

**Section length cap:** each interval string is ignored if it doesn't parse to a
valid offset in `[5 minutes, 14 days]`.

### Confirmation push

After inserting and scheduling reminders for a new event, push:

```
📅 Reminders set for "{event_title}"
{for each reminder:}
  • {human-readable offset} before — {fire_at in local ISO format}

Tell me if you'd like to change these.
```

No inline keyboard — the user can adjust conversationally.

### Startup reminder replay

`CalendarReminderScheduler.start()`:

```python
async with self._pool.acquire() as conn:
    rows = await conn.fetch(
        "SELECT id, fire_at, label FROM calendar_reminders "
        "WHERE sent = false AND fire_at > NOW() ORDER BY fire_at"
    )
for row in rows:
    self._workflow_scheduler.schedule_at(
        fn=lambda r=row: self.fire_reminder(r["id"]),
        dt=row["fire_at"],
        job_id=f"reminder:{row['id']}",
    )
```

### `fire_reminder()` logic

1. Load row from `calendar_reminders` — if already sent or missing, return.
2. Push `label` via `notifier.push()`.
3. Mark `sent = true`, `sent_at = NOW()`.
4. Insert `push_log` row: `event_type = 'calendar_reminder:{id}'`.

---

## Database Schema

Migration `migrations/versions/006_proactive.py`.

```sql
CREATE TABLE push_log (
    id          SERIAL PRIMARY KEY,
    event_type  TEXT NOT NULL,
    payload     TEXT,
    sent_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX push_log_event_type_sent_at_idx ON push_log (event_type, sent_at DESC);

CREATE TABLE calendar_reminders (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id     TEXT NOT NULL,
    event_title  TEXT NOT NULL,
    fire_at      TIMESTAMPTZ NOT NULL,
    label        TEXT NOT NULL,
    assessed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent         BOOLEAN NOT NULL DEFAULT false,
    sent_at      TIMESTAMPTZ
);
CREATE INDEX calendar_reminders_unsent_idx
    ON calendar_reminders (fire_at)
    WHERE sent = false;
CREATE INDEX calendar_reminders_event_id_idx ON calendar_reminders (event_id);
```

---

## Configuration

Add under root in `config/config.yaml`:

```yaml
proactive:
  enabled: true
  briefing_enabled: true
  briefing_cron: "0 8 * * *"           # 8 AM UTC daily
  unreviewed_nudge_threshold: 5         # include nudge if unreviewed >= this
  workflow_failure_alerts: true
  workflow_failure_cooldown_hours: 1    # min hours between repeated failure alerts per workflow
  calendar_sync_enabled: true
  calendar_sync_cron: "45 7 * * *"     # 7:45 AM UTC — before briefing
  calendar_sync_days_ahead: 7
  calendar_reminder_model: anthropic/claude-haiku-4-5
```

All keys have code-level defaults. Read via `settings.proactive_config.get(key, default)`.

---

## Container Wiring

In `build_container()`:

```python
notifier = ProactiveNotifier(bot=bot, chat_id=int(settings.telegram_allowed_chat_id))

# Workflow scheduler gains pool + notifier
workflow_scheduler = WorkflowScheduler(
    ...,
    pool=pool,
    notifier=notifier if settings.proactive_config.get("workflow_failure_alerts", True) else None,
)

# Morning briefing
morning_briefing = MorningBriefing(notifier=notifier, pool=pool, settings=settings)
if settings.proactive_config.get("briefing_enabled", True):
    workflow_scheduler.schedule_job(
        fn=morning_briefing.run,
        cron=settings.proactive_config.get("briefing_cron", "0 8 * * *"),
        job_id="morning_briefing",
    )

# Calendar reminders
google_credentials = GoogleCredentials.from_settings(settings)
calendar_reminders = CalendarReminderScheduler(
    notifier=notifier,
    pool=pool,
    openrouter_client=openrouter_client,
    workflow_scheduler=workflow_scheduler,
    google_credentials=google_credentials,   # None if OAuth env vars not set
    settings=settings,
)
if settings.proactive_config.get("calendar_sync_enabled", True):
    await calendar_reminders.start()   # replay unsent reminders
    workflow_scheduler.schedule_job(
        fn=calendar_reminders.sync,
        cron=settings.proactive_config.get("calendar_sync_cron", "45 7 * * *"),
        job_id="calendar_reminder_sync",
    )
```

`Container` dataclass gains `notifier`, `morning_briefing`, `calendar_reminders` fields.

---

## Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Telegram send fails | `notifier.push()` swallows and logs — no crash |
| Morning briefing already sent today | `push_log` dedup check skips silently |
| Workflow failure cooldown active | `push_log` dedup check skips silently |
| Haiku fails for interval assessment | Fall back to `["1 hour"]` before event |
| Haiku returns malformed JSON | Same fallback |
| Interval is in the past at assessment time | Silently discarded |
| Event rescheduled before reminder fires | Old unsent reminders deleted, re-assessed |
| Google OAuth env vars not set | `google_credentials` is `None` → `sync()` returns immediately |
| `calendar_reminders` row already sent when `fire_reminder` is called | No-op |
| Reminder row missing on `fire_reminder` | No-op, log warning |
| App restart with pending reminders | `start()` reloads and reschedules from DB |
| `allowed_chat_id` not set | `notifier.push()` raises — gated on settings validation |

---

## Testing

| Test | What it verifies |
|------|-----------------|
| `test_notifier_push_sends_message` | `notifier.push()` calls `bot.send_message` with correct chat_id |
| `test_notifier_push_swallows_error` | Telegram exception does not propagate |
| `test_briefing_sends_stats` | `run()` composes correct template and calls `notifier.push` |
| `test_briefing_dedup_skips` | `push_log` row present → `notifier.push` not called |
| `test_briefing_includes_nudge_above_threshold` | unreviewed >= threshold → nudge line in message |
| `test_briefing_no_nudge_below_threshold` | unreviewed < threshold → no nudge line |
| `test_briefing_includes_failure_summary` | recent `push_log` failure rows → failure line in message |
| `test_workflow_failure_alert_fires` | exception in `_run_workflow` → `notifier.push` called |
| `test_workflow_failure_alert_respects_cooldown` | `push_log` row present → alert suppressed |
| `test_workflow_failure_alert_disabled` | `workflow_failure_alerts: false` → no push |
| `test_assess_intervals_parses_json` | valid Haiku response → correct `datetime` list |
| `test_assess_intervals_fallback_on_haiku_error` | Haiku raises → `["1 hour"]` fallback |
| `test_assess_intervals_discards_past` | interval that fires in the past → discarded |
| `test_sync_skips_known_event` | `calendar_reminders` row exists → no re-assessment |
| `test_sync_schedules_new_event` | new event → reminders inserted, `schedule_at` called, confirmation pushed |
| `test_sync_skips_when_no_credentials` | `google_credentials=None` → sync returns immediately, no DB or API calls |
| `test_fire_reminder_pushes_and_marks_sent` | `fire_reminder()` pushes label, sets `sent = true` |
| `test_fire_reminder_noop_when_already_sent` | `sent = true` → no push |
| `test_start_replays_unsent_reminders` | unsent future rows → `schedule_at` called for each |
| `test_schedule_at_uses_date_trigger` | `schedule_at()` registers a `DateTrigger` job |

---

## Open Questions

All resolved.
