# Phase N — <Feature Name>

> **Status:** Pending | In Progress | Done | Deferred | Deprecated
> **Depends on:** Phase X — brief reason this dependency exists
> **Enables:** Phase Y — what this phase unlocks
> **Packages touched:** `core/ze-x`, `plugins/ze-y`, `apps/ze-api`, `apps/ze-web`

---

## Summary

One paragraph. What this phase ships and why it matters. Write it assuming the
reader has no prior context. If there is a user-visible behaviour change, lead
with that.

---

## Goals

- Concrete, verifiable outcome
- ...

## Non-Goals

- What is explicitly out of scope and why (prevents scope creep mid-implementation)
- ...

---

## Background

Context the reader needs. Link to prior phases, arch docs, or external sources.
Skip this section if the Summary is self-contained.

---

## Design

### <Subfeature or Component 1>

Describe the approach. Include sequence diagrams, data flow, or pseudocode where
the prose alone is ambiguous.

### <Subfeature or Component 2>

...

---

## Interface Contract

### Public API changes

<!-- REST routes, Python ABCs, SDK exports. Use `response_model`, `summary`, `operation_id`. -->

### WebSocket frames / events

<!-- New or changed WS frame types. -->

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| ... | ... |

---

## Data Structures

<!-- Key dataclasses. Ze convention: dataclasses in types.py, no Pydantic in domain. -->

```python
# {core,plugins}/<package>/<module>/types.py

@dataclass
class Foo:
    id: str
    ...
```

---

## Database Schema

<!-- Alembic raw SQL. Include table, columns, indexes, FKs. Omit if no DB changes. -->

```sql
CREATE TABLE foo (
    id          TEXT PRIMARY KEY,
    ...
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Migration / Rollout Notes

<!-- DB migrations, feature flags, backwards-compat concerns, rollback plan. Omit for
     purely additive phases with no shared state changes. -->

---

## Configuration

<!-- config.yaml keys or .env vars introduced or changed. -->

```yaml
# config/config.yaml
foo:
  setting: value
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.errors` | Typed error hierarchy |
| ... | ... |

---

## Alternatives Considered

<!-- Why this design over the obvious alternatives. A blank section is a red flag —
     if you genuinely had no alternatives, say so and why. -->

| Option | Why rejected |
|--------|-------------|
| ... | ... |

---

## Testing Strategy

<!-- What tests must exist before this phase is "Done". Be specific. -->

| Layer | What to cover | Approach |
|-------|--------------|----------|
| Unit | ... | pytest mocks, no real DB |
| Integration | ... | real asyncpg, no LLM |
| Eval | ... | YAML scenario in `eval/scenarios/` |

---

## Definition of Done

<!-- Binary checklist. All boxes must be checked before status → Done.
     Update this section as implementation reveals additional required work. -->

- [ ] Core types defined in `types.py`
- [ ] Store layer with unit tests
- [ ] Agent wired and smoke-tested
- [ ] Migration added and stamped
- [ ] Spec header status updated + `specs/README.md` row updated

---

## Architectural Decisions

<!-- Resolved choices that are non-obvious or worth auditing later.
     Move to `arch/` if this decision affects more than one phase. -->

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ... | ... | ... |

---

## Implementation Notes

<!-- Non-obvious invariants, workarounds, or constraints a future reader would
     need. Default: empty. Only add if the WHY is not obvious from the code. -->

---

## Open Questions

<!-- Track unresolved questions. When resolved, append the answer inline and
     strike through or delete the checkbox — do not delete the line.
     Format: `- [ ] Question text — Owner — Target date` -->

- [ ] ...
