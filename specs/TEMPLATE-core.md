# Ze Core — <Module Name> — Spec

> **Package:** `core/ze-<name>` — `ze_<name>/<submodule>/`
> **Status:** Pending | In Progress | Done | Deprecated
> **Phase:** N (link to implementing phase)

---

## Purpose

One paragraph. What problem does this module solve? Why does it exist as a
distinct module rather than code inside its callers?

---

## Responsibilities

<!-- What this module owns, enforces, and guarantees. -->

- ...

---

## Out of Scope

<!-- What explicitly does NOT belong here. Prevents scope creep. -->

- ...

---

## Module Location

```
core/<package>/
  <module>/
    __init__.py
    types.py      ← dataclasses; never Pydantic
    store.py      ← optional persistence layer
    ...
```

---

## Interface Contract

### Public API

```python
# ze_<name>/<submodule>/__init__.py

class FooStore:
    async def get(self, id: str) -> Foo | None: ...
    async def put(self, foo: Foo) -> None: ...
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| ... | ... |

---

## Data Structures

```python
# ze_<name>/<submodule>/types.py

@dataclass
class Foo:
    id: str
    ...
```

---

## Database Schema

<!-- Omit if this module has no DB interaction. -->

```sql
CREATE TABLE foo (
    id          TEXT PRIMARY KEY,
    ...
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_agents.errors` | Typed error hierarchy |
| ... | ... |

---

## Implementation Notes

<!-- Non-obvious invariants, hidden constraints, or workarounds that would
     surprise a reader. Default: empty. -->

---

## Open Questions

<!-- Format: `- [ ] Question text — Owner — Target date` -->

- [ ] ...
