# Calendar Package + API Rename — Spec

> **Packages:** `ze-google` (new), `ze-calendar` (new), `ze-api` (renamed from `ze`)
> **Phase:** 44
> **Status:** Pending
> **Depends on:** Phase 20 ([20-package-reorg.md](20-package-reorg.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze-google` package scaffold | 🔲 Pending |
| `GoogleCredentials` moved to `ze-google` | 🔲 Pending |
| `ze-calendar` package scaffold | 🔲 Pending |
| `CalendarAgent` + tools moved | 🔲 Pending |
| `RemindersAgent` + tools moved | 🔲 Pending |
| `ReminderStore` + `fire_reminder` moved | 🔲 Pending |
| `CalendarReminderService` + `CalendarReminderStore` moved | 🔲 Pending |
| `CalendarReminderJob` moved | 🔲 Pending |
| `CalendarPlugin(ZePlugin)` created | 🔲 Pending |
| `ze_calendar/timezone/` module (new) | 🔲 Pending |
| `ze` directory renamed → `ze_api` | 🔲 Pending |
| `ze-api` package name + pyproject.toml updated | 🔲 Pending |
| All internal imports updated | 🔲 Pending |
| Migrations path unchanged | 🔲 Pending |
| Tests updated + passing | 🔲 Pending |

---

## Purpose

Ze's calendar, reminder, and timezone logic currently lives inside the `ze` application
package alongside FastAPI routes, Telegram bot code, and proactive jobs. This makes
`ze` a monolith that mixes infrastructure concerns with domain logic.

This phase extracts two clean domain packages:

- **`ze-google`** — shared Google OAuth2 credentials and service client factories. No
  business logic; other packages depend on this for authentication without importing
  each other.
- **`ze-calendar`** — all calendar and reminder domain logic: agents, tools, stores,
  jobs, a `ZePlugin`, and a new timezone utility module. Depends on `ze-google` for
  credentials, `ze-core` for orchestration primitives, and optionally `ze-personal` for
  contact extraction from calendar events.

The `ze` package is also renamed to `ze-api` to accurately reflect its role: it is the
deployment unit that wires plugins together and exposes the HTTP/WebSocket API. Domain
logic no longer lives there.

---

## New Dependency Graph

```
ze-browser    (no ze deps)         — unchanged
ze-core       (no ze deps)         — unchanged
ze-personal → ze-core              — unchanged
ze-google     (no ze deps)         — NEW: Google OAuth2 credentials
ze-calendar → ze-core, ze-google   — NEW: calendar + reminders domain
ze-api      → ze-core, ze-personal, ze-calendar, ze-google,
               ze-browser, ze-news, ze-notifications, ze-components
               (renamed from ze)
```

`ze-google` has no Ze dependencies so it could be extracted further in future (e.g.,
shared with a hypothetical `ze-communications` package housing Gmail, Contacts export,
etc.) without circular imports.

---

## Out of Scope

- Moving `GmailChannel` or the email agent — they stay in `ze-api` for now. They import
  `GoogleCredentials` from `ze-google` after this phase.
- Moving the Telegram bot, FastAPI app, or proactive jobs (other than the calendar job).
- A `ze-reminders` package separate from `ze-calendar` — reminders are calendar-adjacent
  and share the timezone module; splitting them would add a dependency edge without
  architectural benefit.
- Migrating the database — schema is unchanged, only Python module paths change.
- New calendar features beyond the timezone module.

---

## Package: `ze-google`

### Location

```
packages/ze-google/
  pyproject.toml
  ze_google/
    __init__.py       ← exports GoogleCredentials
    auth.py           ← moved from ze/google/auth.py, unchanged
```

### What moves

`ze/google/auth.py` moves verbatim. The `SCOPES` constant stays in `auth.py` since it
covers all Google APIs Ze currently uses; splitting scopes per-service is future scope.

`ze/google/gmail.py` and `ze/google/__init__.py` stay in `ze-api` but update their
import to `from ze_google.auth import GoogleCredentials`.

### `pyproject.toml`

```toml
[project]
name = "ze-google"
version = "0.1.0"
description = "Shared Google OAuth2 credentials for Ze packages."
requires-python = ">=3.12"
dependencies = [
    "google-api-python-client>=2.0",
    "google-auth>=2.0",
    "google-auth-oauthlib>=1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ze_google"]
```

No `ze-core` dependency — `ze-google` is deliberately infrastructure-only.

---

## Package: `ze-calendar`

### Location

```
packages/ze-calendar/
  pyproject.toml
  ze_calendar/
    __init__.py
    plugin.py                  ← CalendarPlugin(ZePlugin)
    agents/
      calendar/
        __init__.py            ← imports tools module (side-effect registration)
        agent.py               ← CalendarAgent (moved from ze/agents/calendar/)
        tools.py               ← list_events, create_event, update_event, delete_event
      reminders/
        __init__.py
        agent.py               ← RemindersAgent (moved from ze/agents/reminders/)
        tools.py               ← set_reminder, list_reminders, cancel_reminder
    reminders/
      __init__.py
      store.py                 ← ReminderStore, fire_reminder (moved from ze/reminders/store.py)
      calendar_store.py        ← CalendarReminderStore (moved from ze/reminders/calendar_store.py)
      calendar.py              ← CalendarReminderService (moved from ze/reminders/calendar.py)
    jobs/
      __init__.py
      calendar_reminder.py     ← CalendarReminderJob (moved from ze/jobs/calendar.py)
    timezone/
      __init__.py              ← exports TimezoneService, world_time tool
      service.py               ← TimezoneService
      tools.py                 ← world_time @tool
```

### What moves

| From (`ze/`) | To (`ze_calendar/`) | Notes |
|---|---|---|
| `agents/calendar/agent.py` | `agents/calendar/agent.py` | Import paths updated |
| `agents/calendar/tools.py` | `agents/calendar/tools.py` | `ze.google.auth` → `ze_google.auth` |
| `agents/reminders/agent.py` | `agents/reminders/agent.py` | `ze.reminders.store` → `ze_calendar.reminders.store` |
| `agents/reminders/tools.py` | `agents/reminders/tools.py` | Same |
| `reminders/store.py` | `reminders/store.py` | `ze.logging` → `ze_core.logging` (or equivalent) |
| `reminders/calendar_store.py` | `reminders/calendar_store.py` | Same |
| `reminders/calendar.py` | `reminders/calendar.py` | All `ze.*` imports updated |
| `jobs/calendar.py` | `jobs/calendar_reminder.py` | Renamed for clarity |

### `CalendarPlugin`

```python
# ze_calendar/plugin.py

from ze_core.plugin import ZePlugin

class CalendarPlugin(ZePlugin):
    """Registers calendar + reminder agents, stores, and the calendar reminder job."""

    def register_agents(self, registry) -> None:
        from ze_calendar.agents.calendar import agent  # noqa: F401
        from ze_calendar.agents.reminders import agent  # noqa: F401

    def extend_graph(self, builder) -> None:
        pass  # no graph extensions in this phase

    def get_stores(self) -> dict:
        return {}  # stores are wired directly in ze-api's container
```

`CalendarPlugin` is registered in `ze-api`'s `ZeContainer` alongside `PersonalPlugin`.
Store construction (pool injection) stays in `ZeContainer` — the plugin is responsible
for agent registration, not DI wiring.

### `pyproject.toml`

```toml
[project]
name = "ze-calendar"
version = "0.1.0"
description = "Calendar, reminders, and timezone domain logic for Ze."
requires-python = ">=3.12"
dependencies = [
    "ze-core",
    "ze-google",
    "ze-personal",     # contact extraction from calendar events
    "apscheduler>=3.10",
    "asyncpg>=0.30",
    "structlog>=24.4",
]

[tool.uv.sources]
ze-core     = { workspace = true }
ze-google   = { workspace = true }
ze-personal = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ze_calendar"]
```

---

## New Module: `ze_calendar/timezone/`

### Purpose

A dedicated timezone module gives agents reliable, testable primitives for:
- Resolving a human-readable location or timezone name to an IANA key
  (`"London"` → `"Europe/London"`).
- Formatting a UTC datetime in a target timezone.
- Answering world-clock queries without an LLM round-trip.

Uses only the stdlib `zoneinfo` module (Python 3.9+) — no `pytz` dependency.

### `TimezoneService`

```python
# ze_calendar/timezone/service.py

import zoneinfo
from datetime import datetime, timezone

class TimezoneService:

    def resolve(self, name: str) -> str:
        """Return the IANA key for a common city or timezone alias.

        Falls back to treating `name` as a raw IANA key if not in the alias table.
        Raises ValueError if the key is unrecognised by zoneinfo.
        """
        ...

    def now_in(self, tz_name: str) -> datetime:
        """Return the current wall-clock time in the given timezone."""
        tz = zoneinfo.ZoneInfo(self.resolve(tz_name))
        return datetime.now(tz)

    def convert(self, dt: datetime, to_tz: str) -> datetime:
        """Convert a timezone-aware datetime to a different timezone."""
        tz = zoneinfo.ZoneInfo(self.resolve(to_tz))
        return dt.astimezone(tz)

    def format(self, dt: datetime, tz_name: str, fmt: str = "%Y-%m-%d %H:%M %Z") -> str:
        """Format a UTC datetime as a local time string in the given timezone."""
        return self.convert(dt, tz_name).strftime(fmt)
```

### City alias table

A hardcoded `dict[str, str]` covering the ~30 most common cities Ze is likely to
encounter. Keys are lowercase city names and common aliases; values are IANA zone IDs.

```python
_ALIASES = {
    "london":        "Europe/London",
    "lisbon":        "Europe/Lisbon",
    "paris":         "Europe/Paris",
    "berlin":        "Europe/Berlin",
    "new york":      "America/New_York",
    "nyc":           "America/New_York",
    "los angeles":   "America/Los_Angeles",
    "la":            "America/Los_Angeles",
    "chicago":       "America/Chicago",
    "toronto":       "America/Toronto",
    "são paulo":     "America/Sao_Paulo",
    "sao paulo":     "America/Sao_Paulo",
    "dubai":         "Asia/Dubai",
    "mumbai":        "Asia/Kolkata",
    "delhi":         "Asia/Kolkata",
    "singapore":     "Asia/Singapore",
    "hong kong":     "Asia/Hong_Kong",
    "shanghai":      "Asia/Shanghai",
    "beijing":       "Asia/Shanghai",
    "tokyo":         "Asia/Tokyo",
    "seoul":         "Asia/Seoul",
    "sydney":        "Australia/Sydney",
    "melbourne":     "Australia/Melbourne",
    "auckland":      "Pacific/Auckland",
    "utc":           "UTC",
    "gmt":           "UTC",
}
```

### `world_time` tool

```python
# ze_calendar/timezone/tools.py

from ze_core.orchestration.tool import ToolAccess, tool
from ze_calendar.timezone.service import TimezoneService

@tool(access=ToolAccess.READ, description=(
    "Return the current local time in one or more cities or IANA timezone names. "
    "Pass a list of city names or timezone strings (e.g. ['London', 'Tokyo', 'UTC'])."
))
async def world_time(
    timezone_service: TimezoneService,
    locations: list[str],
) -> list[dict]:
    results = []
    for loc in locations:
        try:
            dt = timezone_service.now_in(loc)
            results.append({
                "location": loc,
                "iana":     timezone_service.resolve(loc),
                "time":     dt.strftime("%Y-%m-%d %H:%M"),
                "tz_abbr":  dt.strftime("%Z"),
                "utc_offset": dt.strftime("%z"),
            })
        except (ValueError, KeyError) as e:
            results.append({"location": loc, "error": str(e)})
    return results
```

The `world_time` tool is added to `CalendarAgent.tools` so Ze can answer
"What time is it in Tokyo right now?" without a dedicated agent round-trip. It is
injected via the standard `@tool` dependency injection already used by calendar tools.

---

## Package: `ze-api` (renamed from `ze`)

### Rename steps

1. Rename directory: `packages/ze/ze/` → `packages/ze/ze_api/`
2. Update `packages/ze/pyproject.toml`:
   - `name = "ze"` → `name = "ze-api"`
   - `packages = ["ze"]` → `packages = ["ze_api"]`
   - Add `ze-calendar = { workspace = true }` and `ze-google = { workspace = true }`
   - Remove `apscheduler`, `google-api-python-client`, `google-auth`, `google-auth-oauthlib`
     from direct dependencies (now pulled in transitively via `ze-calendar` / `ze-google`)
3. Rename `packages/ze/` directory → `packages/ze-api/`
4. Update root `pyproject.toml` uv workspace exclusion: `packages/ze-app` stays excluded
5. Update `Makefile` targets that reference `packages/ze/`

### Import updates inside `ze-api`

Every file in `ze_api/` that imports from the moved modules is updated:

| Old import | New import |
|---|---|
| `from ze.google.auth import GoogleCredentials` | `from ze_google.auth import GoogleCredentials` |
| `from ze.google.gmail import GmailChannel` | `from ze_api.google.gmail import GmailChannel` |
| `from ze.reminders.store import ReminderStore, fire_reminder` | `from ze_calendar.reminders.store import ReminderStore, fire_reminder` |
| `from ze.reminders.calendar_store import CalendarReminderStore` | `from ze_calendar.reminders.calendar_store import CalendarReminderStore` |
| `from ze.reminders.calendar import CalendarReminderService` | `from ze_calendar.reminders.calendar import CalendarReminderService` |
| `from ze.jobs.calendar import CalendarReminderJob` | `from ze_calendar.jobs.calendar_reminder import CalendarReminderJob` |
| `from ze.agents.calendar import ...` | removed — registered via `CalendarPlugin` |
| `from ze.agents.reminders import ...` | removed — registered via `CalendarPlugin` |
| `from ze.logging import get_logger` | `from ze_core.logging import get_logger` (see note) |
| All other `from ze.` | `from ze_api.` |

**Note on `ze.logging`:** `ze/logging.py` is a thin re-export of `structlog`. If it
already delegates to `ze_core`, the import update is cosmetic. If not, move it to
`ze_core` as part of this phase to avoid a circular dependency.

### `ZeContainer` changes

- Register `CalendarPlugin` alongside `PersonalPlugin`.
- `GoogleCredentials` is constructed from settings and passed to `CalendarPlugin` (or
  directly to store constructors) rather than being imported from `ze.google.auth`.
- `ReminderStore`, `CalendarReminderStore`, `CalendarReminderService`,
  `CalendarReminderJob` are all imported from `ze_calendar.*`.

### What stays in `ze-api`

- `ze_api/api/` — FastAPI app, WebSocket endpoint, REST routes
- `ze_api/google/gmail.py` — `GmailChannel` (email-specific, not shared infra)
- `ze_api/agents/email/` — email agent
- `ze_api/agents/companion/`, `research/`, `prospecting/`, `testing/`
- `ze_api/jobs/` (minus `calendar.py` which moves to `ze-calendar`)
- `ze_api/telegram/` — Telegram bot
- `ze_api/container.py`, `ze_api/settings.py`, `ze_api/errors.py`
- `ze_api/interface/` — `NativeAppInterface`
- `ze_api/migrations/` — path unchanged; Alembic `env.py` imports updated

---

## Migration Checklist

Order matters — each step leaves the tests passing before the next begins.

1. **Create `ze-google`**
   - Copy `auth.py`, write `pyproject.toml`, add to workspace.
   - Update `ze/google/gmail.py`, `ze/agents/email/`, `ze/container.py` to import from
     `ze_google.auth`. Run tests.

2. **Create `ze-calendar` scaffold**
   - Empty package with `pyproject.toml`. Add to workspace. Run tests (no-op).

3. **Move reminders**
   - Move `ze/reminders/` → `ze_calendar/reminders/`.
   - Update all `ze.reminders.*` imports. Run tests.

4. **Move calendar + reminders agents**
   - Move `ze/agents/calendar/` and `ze/agents/reminders/` to `ze_calendar/agents/`.
   - Move `ze/jobs/calendar.py` → `ze_calendar/jobs/calendar_reminder.py`.
   - Add `CalendarPlugin`, register in container. Run tests.

5. **Add timezone module**
   - Write `ze_calendar/timezone/service.py`, `tools.py`.
   - Add `world_time` to `CalendarAgent.tools`. Write tests.

6. **Rename `ze` → `ze-api`**
   - Rename directory, update `pyproject.toml`, rewrite all remaining `from ze.`
     imports to `from ze_api.`. Run full test suite.

7. **Update `CLAUDE.md`** — dependency graph, package list, phase table.

---

## Alembic / migrations

Alembic `env.py` references `ze.settings.Settings`. After rename this becomes
`ze_api.settings.Settings`. The `migrations/` directory itself stays at
`packages/ze-api/migrations/` (was `packages/ze/migrations/`). The `Makefile`
`migrate` target is updated to point to the new path.

No schema changes in this phase.

---

## Tests

Existing tests move with their modules. New tests for the timezone module:

| Test | Location |
|------|----------|
| `TimezoneService.resolve` returns correct IANA key for aliases | `tests/timezone/service_test.py` |
| `TimezoneService.resolve` accepts raw IANA key (`"Europe/Paris"`) | same |
| `TimezoneService.resolve` raises `ValueError` for unknown name | same |
| `TimezoneService.now_in` returns a timezone-aware datetime | same |
| `world_time` tool returns time + offset for a list of locations | `tests/timezone/tools_test.py` |
| `world_time` tool includes error entry for unknown location | same |

---

## Open Questions

- [ ] **`ze.logging` re-export.** Confirm whether `ze/logging.py` is a pass-through to
  `ze_core` or adds something. If it's just `from ze_core.logging import get_logger`,
  delete it and update callers directly.
- [ ] **`ze-personal` dependency on `ze-calendar`.** `ze_personal` currently does not
  depend on `ze_calendar`, and this phase keeps it that way. If contact extraction from
  calendar events grows into a shared concern, that dependency can be introduced then.
