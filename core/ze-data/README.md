# ze-data

Pure-infrastructure data management layer — `DataDomain` descriptor and `DataPortabilityService`. Has no Ze package dependencies and no domain knowledge; it sits at the base of the dependency graph alongside `ze-agents`.

## Role in Ze

`ze-data` owns two things: the `DataDomain` descriptor (what a domain is and how to export/import/delete it) and the `DataPortabilityService` that orchestrates those operations across all registered domains.

Plugin authors implement `ZePlugin.data_domains()` returning a list of `DataDomain` instances. `DataPortabilityService` receives the collected list at construction time in `ze-api` and calls each domain's callables as needed.

### Key features

- `DataDomain` dataclass — the contract between a plugin and the portability service
- `DataPortabilityService` — export to ZIP, import from ZIP, hard-delete with token-gated confirmation
- `ExportAssembler` / `ImportAssembler` — ZIP archive construction and parsing
- `SchemaMismatchError` / `InstanceNotEmptyError` — typed errors for portability failures

### Integration

`ze-plugin` imports `DataDomain` from `ze-data` and re-exports it for backwards compatibility. `ze-api` wires `DataPortabilityService` in the container and exposes it via `/api/data/*` routes.

## Responsibilities

| Module | What it provides |
|---|---|
| `domain.py` | `DataDomain` dataclass |
| `errors.py` | `SchemaMismatchError`, `InstanceNotEmptyError` |
| `portability/service.py` | `DataPortabilityService` |
| `portability/assembler.py` | `ExportAssembler`, `ImportAssembler`, `bulk_insert` |
| `portability/types.py` | `ExportManifest`, `ImportResult` |

## Dependencies

No Ze package dependencies. Stdlib only: `asyncio`, `zipfile`, `json`, `logging`.

## Usage

Plugin authors declare data domains via `ZePlugin.data_domains()`:

```python
from ze_data import DataDomain

DataDomain(
    name="my_plugin.records",
    export=lambda pool: ...,          # async, returns list[dict]
    delete=lambda pool: ...,          # async, returns None
    delete_order=50,
    importer=lambda conn, rows: ...,  # async, returns int (rows inserted); None = not importable
)
```

`delete_order` controls sequencing: lower values are deleted first (children before parents). Import runs in reverse (parents first).

`ze-plugin` and `ze-sdk` import `DataDomain` directly from `ze_data.domain`. Plugin authors access it via `ze_sdk` as usual.

## Testing

From the repo root:

```bash
make test-data
```

See [docs/testing.md](../../docs/testing.md).
