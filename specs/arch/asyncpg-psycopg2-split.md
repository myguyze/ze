# ADR: asyncpg for runtime, psycopg2 for Alembic CLI

> **Status:** Accepted
> **Date:** 2023-11-01 (Phase 1)
> **Scope:** All Postgres access across every package

---

## Context and Problem Statement

Ze needs a Postgres driver for both runtime queries (async FastAPI handlers, background
jobs) and schema migrations (Alembic CLI). The simplest path would be one driver for
both. The constraint is that asyncpg has no synchronous mode and Alembic's CLI requires
a synchronous connection.

---

## Decision Drivers

- All runtime I/O is async — no `asyncio.run()` inside a running event loop
- Alembic CLI runs outside the event loop and requires a sync `engine` (psycopg2 or
  psycopg3)
- Minimise the number of runtime dependencies
- `DATABASE_URL` (asyncpg) and `DATABASE_URL_SYNC` (psycopg2) are already separate
  env vars

---

## Considered Options

1. **psycopg2 everywhere** — use `asyncpg`-style wrappers or `asyncpg_compat` shims
2. **psycopg3 everywhere** — supports both async and sync modes in one package
3. **asyncpg runtime + psycopg2 Alembic** — two drivers, each used only where it fits

---

## Decision Outcome

**Chosen option: asyncpg runtime + psycopg2 Alembic (Option 3).**

asyncpg is the fastest Postgres driver for Python async code. It is what the codebase
was built on from day one. Alembic is CLI-only and never runs in the hot path, so
psycopg2 there has no performance impact. The split is explicit in `.env` via two
separate `DATABASE_URL_*` vars.

### Positive Consequences

- asyncpg's performance and binary protocol for all runtime queries
- Alembic migrations work without workarounds
- Both drivers are stable, well-maintained, and widely understood

### Negative Consequences / Trade-offs

- Two drivers to install and keep updated
- New contributors are frequently confused by the split — the reason (asyncpg has
  no sync mode) must be documented (see CLAUDE.md) or they try to use one URL for both
- `asyncpg.Pool` vs SQLAlchemy engine means no shared abstraction layer

---

## Pros and Cons of the Options

### Option 1 — psycopg2 everywhere

**Cons:** psycopg2 in async code requires `run_sync` wrappers which block the event
loop or require thread pool overhead. Not acceptable for the runtime path.

### Option 2 — psycopg3 everywhere

**Pros:** One package, one install, both sync and async.

**Cons:** psycopg3 was not stable at project start; asyncpg already had years of
production use. Migrating now would be a significant mechanical change for no runtime
benefit.

### Option 3 — asyncpg + psycopg2

**Pros:** Each driver used where it fits naturally. No wrappers or shims.

**Cons:** The split is invisible until it bites someone. Mitigated by the two-URL
env var convention and documentation.

---

## Links

- `apps/ze-api/ze_api/` — `DATABASE_URL` and `DATABASE_URL_SYNC` in `settings.py`
- `apps/ze-api/ze_api/migrate.py` — meta-runner using psycopg2-backed Alembic
