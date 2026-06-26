# Phase 96 — Dev Data Seeder

> **Package:** `ze_seed`
> **Phase:** 96
> **Status:** Done
> **Depends on:** Phase 62 (data portability), Phase 20 (ZePlugin)

---

## Implementation Status

| Feature | Status |
|---------|--------|
| SeedDomain + DevDataSeeder | Done |
| Narrative YAML fixtures | Done |
| Memory / automation / engine domains | Done |
| Plugin seed domains (personal, calendar) | Done |
| Startup + CLI wiring | Done |
| Tests | Done |

---

## Purpose

Ze is hard to test and develop against on an empty database. The dev data seeder populates
a curated narrative persona (`seed-dev-*` namespace) on startup when `AUTO_SEED_DEV_DATA=true`
(default via `make dev`). Each run clears prior seed-namespace rows and re-applies fixtures,
leaving user-created data untouched.

---

## Responsibilities

- Define `SeedDomain` — parallel to `DataDomain` — with `clear` and `apply` callables
- Orchestrate seed domains in FK-safe order via `DevDataSeeder`
- Load fixture definitions from `persona.yaml` with stable UUIDs
- Write memory facts/episodes through store APIs (embeddings computed correctly)
- Register plugin seed domains via `ZePlugin.seed_domains()`
- Expose CLI (`python -m ze_seed apply`) and Makefile targets

---

## Out of Scope

- Production seeding (guarded by `AUTO_SEED_DEV_DATA`)
- Live feeds: news RSS, Gmail, ingestion pipeline
- Finance / prospecting fixtures (v1.1)
- Faker-generated random data
- Merge import into non-empty instances (portability concern)

---

## Module Location

```
core/ze-seed/
  ze_seed/
    domain.py
    context.py
    service.py
    bootstrap.py
    narrative/
      persona.yaml
      loader.py
      ids.py
    domains/
      memory.py
      automation.py
      engine.py
  tests/
```

Plugin hooks: `plugins/ze-personal/ze_personal/seed.py`, `plugins/ze-calendar/ze_calendar/seed.py`

---

## Interface Contract

### SeedDomain

```python
@dataclass
class SeedDomain:
    name: str
    seed_order: int
    clear: Callable[[SeedContext], Awaitable[None]]
    apply: Callable[[SeedContext], Awaitable[int]]
```

- **clear** runs in ascending `seed_order` (children first)
- **apply** runs in descending `seed_order` (parents first)

### DevDataSeeder

```python
class DevDataSeeder:
    async def apply(self, *, force: bool = True) -> dict[str, int]
```

When `force=True`, all domains are cleared before apply.

### ZePlugin hook

```python
def seed_domains(self) -> list[SeedDomain]:
    return []
```

---

## Namespace Rules

| Domain | Marker |
|--------|--------|
| Episodes | `session_id: seed-dev-main` |
| Messages | `thread_id: seed-dev-chat` |
| Goals, milestones, gates, traces, learnings | Fixed fixture UUIDs in `ids.py` |
| Contacts, reminders | Fixed fixture UUIDs |
| Onboarding | Fixed session UUID |

Clear deletes only rows matching these markers.

---

## v1 Fixture Inventory

**Persona:** Alex — software engineer learning Portuguese, prefers async communication.

- **Memory:** ~12 facts, ~6 episodes across companion/calendar/research agents
- **Goals:** 3 (active Portuguese B1, completed side project, planning sleep routine)
- **Messages:** ~8 chat turns with traces on assistant messages
- **Contacts:** 3 (manager, tutor, partner)
- **Calendar:** 2 reminders
- **Persona:** direct communication style
- **Onboarding:** one completed session

---

## Configuration

```bash
# .env — make dev sets AUTO_SEED_DEV_DATA=true
AUTO_SEED_DEV_DATA=false
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-memory` | MemoryStore, Fact types |
| `ze-automation` | GoalStore, goal types |
| `ze-core` | MessageStore, SessionStore |
| `ze-logging` | Structured logging |
| `ze-onboarding` | Onboarding session tables |

---

## Relationship to Existing Systems

| System | Relationship |
|--------|--------------|
| `DataPortabilityService` | Complementary — full export/import vs dev-only namespace |
| `ResetService` | Unchanged — manual full wipe via `CONFIRM=RESET` |
| Eval fixtures | Separate `eval-*` namespace |
