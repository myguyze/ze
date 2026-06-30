# ze-proactive — Job Scheduling Framework

> **Package:** `core/ze-proactive` — `ze_proactive/`
> **Status:** Done
> **Implemented in:** [Phase 48](../phases/48-core-split.md) (extracted from ze-core)

---

## Purpose

Provides the substrate for all background jobs in Ze: the `ProactiveJob` ABC,
`ProactiveScheduler` (APScheduler wrapper), `ProactiveNotifier` (sends push
notifications from jobs), and `PushLogStore` (dedup / rate-limiting). Domain jobs
(briefing, insights, goal sweeps, calendar reminders) subclass `ProactiveJob` and
register with `ProactiveScheduler` at startup.

---

## Responsibilities

- `ProactiveJob` ABC — `job_id`, `schedule` (cron string), `run(container)` async method
- `ProactiveScheduler` — wraps APScheduler; registers jobs, starts/stops the scheduler,
  handles misfire grace and coalescing
- `ProactiveNotifier` — sends ntfy push notifications from job context; thin wrapper
  over `ze-notifications`
- `PushLogStore` / `PostgresPushLogStore` — persists push log for dedup (prevents
  firing the same notification twice in a window)
- Migrations — `zpro` chain for `push_log` table

---

## Out of Scope

- Push notification delivery — `ze-notifications`
- Job implementations (briefing, insights, reminders, etc.) — plugin packages
- Job registration fan-out — `ze-api/compose.py`

---

## Module Location

```
core/ze-proactive/ze_proactive/
  job.py              ← ProactiveJob ABC
  scheduler.py        ← ProactiveScheduler (APScheduler wrapper)
  notifier.py         ← ProactiveNotifier
  push_log_store.py   ← PushLogStore Protocol + PostgresPushLogStore
  migrations/         ← zpro chain (push_log table)
  migrate.py          ← migration runner entry
```

---

## Interface Contract

```python
class ProactiveJob(ABC):
    job_id: str          # unique across all jobs
    schedule: str        # cron string, e.g. "0 8 * * *"

    @abstractmethod
    async def run(self, container: BaseContainer) -> None: ...

# Registration (in ze-api/compose.py)
scheduler.register(MyJob())
await scheduler.start()
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `BaseContainer`, `Settings` |
| `ze-logging` | `get_logger` |
| APScheduler | Cron scheduling |
