# ze-data — Spec

> **Package:** `core/ze-data`
> **Phase:** 68
> **Status:** Pending

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `DataDomain` extracted from `ze-plugin` | ✅ Done |
| `DataPortabilityService` migrated from `ze-api` | ✅ Done |
| Assemblers and portability types migrated | ✅ Done |
| Shims in `ze-plugin` and `ze-sdk` | ✅ Done |
| `ze-api/data/` deleted | ✅ Done |
| Tests migrated | ✅ Done |

---

## Purpose

`ze-data` is a pure-infrastructure core package that owns two things: the `DataDomain`
descriptor (what a domain is and how to export/import/delete it) and the
`DataPortabilityService` that orchestrates export, import, and deletion across all
registered domains.

Currently `DataDomain` lives in `ze-plugin` (wrong layer — plugin framework should not
own a data type) and `DataPortabilityService` lives in `ze-api/data/` (wrong layer —
portability logic is infrastructure, not API). This phase extracts both into
`ze-data` where they belong.

`ze-data` has no LLM dependency and no domain knowledge. It is the lowest-level
data-management layer in the stack.

---

## Responsibilities

- Define the `DataDomain` descriptor (export / import / delete callables + ordering)
- Implement `DataPortabilityService` (orchestrate export, import, hard-delete across domains)
- Own `ExportAssembler` and `ImportAssembler` (ZIP archive construction and parsing)
- Own portability types: `ExportManifest`, `ImportResult`
- Provide a stable public API re-exported from `ze_data`

---

## Out of Scope

- Any LLM calls or AI logic
- Domain-specific export/import logic (that belongs in each plugin's `data_domains()`)
- HTTP routes for data export/import/delete (those stay in `ze-api/data/routes.py`)
- Ingestion pipeline (Phase 69)

---

## Module Location

```
core/ze-data/
└── ze_data/
    ├── __init__.py       # public re-exports: DataDomain, DataPortabilityService, types
    ├── domain.py         # DataDomain dataclass
    ├── portability/
    │   ├── __init__.py
    │   ├── service.py    # DataPortabilityService (moved from ze-api/data/service.py)
    │   ├── assembler.py  # ExportAssembler, ImportAssembler (moved from ze-api/data/assembler.py)
    │   └── types.py      # ExportManifest, ImportResult (moved from ze-api/data/types.py)
    └── errors.py         # SchemaMismatchError, InstanceNotEmptyError
```

---

## Interface Contract

### `DataDomain`

```python
# ze_data/domain.py

@dataclass
class DataDomain:
    name: str
    export: Callable[[Any], Awaitable[list[dict]]]
    delete: Callable[[Any], Awaitable[None]]
    delete_order: int = 50
    importer: Callable[[Any, list[dict]], Awaitable[int]] | None = None
```

No behaviour change from the current definition in `ze-plugin`.

### `DataPortabilityService`

```python
# ze_data/portability/service.py

class DataPortabilityService:
    def __init__(self, pool: Any, domains: list[DataDomain]) -> None: ...

    async def get_schema_revisions(self) -> list[str]: ...
    async def export(self) -> bytes: ...
    async def is_empty(self) -> bool: ...
    async def import_archive(self, archive_bytes: bytes) -> ImportResult: ...
    def create_delete_intent(self) -> tuple[str, datetime]: ...
    def consume_delete_intent(self, token: str) -> bool: ...
    async def delete(self) -> None: ...
```

No behaviour change from the current implementation in `ze-api/data/service.py`.

### Errors

| Condition | Error |
|-----------|-------|
| Archive schema revisions don't match current | `SchemaMismatchError` |
| Import attempted on non-empty instance | `InstanceNotEmptyError` |

---

## Data Structures

```python
# ze_data/portability/types.py

@dataclass
class ExportManifest:
    exported_at: datetime
    schema_revisions: list[str]
    domains: list[str]

@dataclass
class ImportResult:
    domains_imported: list[str]
    rows_imported: dict[str, int]
```

---

## Database Schema

None — `ze-data` does not own any tables. The `alembic_version` table it reads is
owned by the migration meta-runner in `ze-api`.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| stdlib only | ZIP assembly, JSON serialisation, asyncio |

No Ze package dependencies. `ze-data` sits at the same dep level as `ze-agents`
(pure infra, no Ze imports).

---

## Migration: existing code

### `ze-plugin` shim

`DataDomain` moves to `ze_data.domain`. Add a re-export shim in `ze-plugin` so no
plugin code needs to change:

```python
# ze_plugin/plugin.py  — keep this line, add import from ze_data
from ze_data.domain import DataDomain  # re-exported for backwards compat
```

`ze-plugin` gains `ze-data` as a dependency.

### `ze-sdk` shim

`ze_sdk.__init__` already re-exports `DataDomain` from `ze_plugin`. No change needed —
the shim chain handles it automatically.

### `ze-api` cleanup

- `ze_api/data/service.py`, `assembler.py`, `types.py` → deleted after migration
- `ze_api/data/routes.py` → updated to import from `ze_data` instead
- `ze_api/data/__init__.py` → deleted
- `ze_api/container.py` → import `DataDomain` from `ze_data` (or keep via `ze_sdk` shim)
- `ze-data` added to `ze-api/pyproject.toml` dependencies

### `ze-api/data/routes.py` import changes

```python
# Before
from ze_api.data.service import DataPortabilityService, SchemaMismatchError, InstanceNotEmptyError
from ze_api.data.types import ImportResult

# After
from ze_data.portability.service import DataPortabilityService, SchemaMismatchError, InstanceNotEmptyError
from ze_data.portability.types import ImportResult
```

---

## Dependency graph after this phase

```
ze-data       (no ze deps)                                        core/
ze-agents     (no ze deps)                                        core/
ze-plugin   → ze-agents, ze-data                                  core/
ze-sdk      → ze-agents, ze-data, ze-plugin, ze-proactive, ze-memory  core/
```

---

## Implementation Notes

- This phase is a pure structural migration — zero behaviour changes. All logic moves
  verbatim; the only edits are import paths.
- `SchemaMismatchError` and `InstanceNotEmptyError` move to `ze_data/errors.py`.
  Keep re-exports in `ze_api/data/` until the routes file is updated, then delete.
- Run `make test` and `make test-core` after migration to confirm no regressions.

---

## Open Questions

- [x] Should `ze-data` depend on `ze-agents` for logging? **Decision: no.** Use stdlib
  `logging` directly in `ze-data` (or a thin local wrapper). `ze-data` must have zero
  Ze imports to stay at the base infra tier.
