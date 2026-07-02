# Phase 100 — Data Dashboard

> **Status:** In Progress
> **Depends on:** Phase 68 (ze-data), Phase 62 (data portability), Phase 72 (API client codegen), Phase 82 (ze-web FSD)

---

## Problem

Ze accumulates data across many domains (memory, contacts, goals, workflows, telemetry, …) but the web app has no way for the user to see what is actually stored or how much. The only data-facing UI is the export/import/delete section buried in Settings, which operates on the data but never shows it.

Adding a dedicated read-only **Data** page under the System umbrella gives the user visibility into the active data domains Ze tracks, per-domain record counts, storage footprint, and a visual breakdown of what is taking space.

---

## Goals

1. Add `count` and `size_bytes` callables to `DataDomain` so each domain can expose row count and `pg_total_relation_size` disk usage.
2. Expose `GET /api/v0/data/domains` returning domain metadata, live counts, per-domain sizes, and aggregate totals.
3. Add a `/data` page under the System umbrella — wide two-column layout (matching Costs), hero storage total, donut chart by category, and per-domain breakdown with size bars.
4. Keep export/import/delete in **Settings** — this page is purely observational.

---

## Out of Scope

- Moving export/import/delete out of Settings.
- Per-domain drill-down or row browsing.
- Historical count/size tracking / trends.
- Filtering or searching domains.

---

## Architecture

### 1. `DataDomain.count` and `DataDomain.size_bytes`

```python
# core/ze-data/ze_data/domain.py

@dataclass
class DataDomain:
    name: str
    export: Callable[[Any], Awaitable[list[dict]]]
    delete: Callable[[Any], Awaitable[None]]
    delete_order: int = 50
    importer: Callable[[Any, list[dict]], Awaitable[int]] | None = None
    # Optional fast count query. None = count not available (shown as null in API).
    count: Callable[[Any], Awaitable[int]] | None = None
    # Optional pg_total_relation_size sum in bytes. None = size not available (0 in API).
    size_bytes: Callable[[Any], Awaitable[int]] | None = None
```

Single-table domains use `_size(tbl)`; multi-table domains (onboarding, checkpoints, finance.recurring) sum their tables.

### 2. `DataPortabilityService.list_domain_summaries()`

```python
@dataclass
class DomainSummary:
    name: str
    importable: bool
    count: int | None
    size_bytes: int  # 0 when domain has no size_bytes callable

async def list_domain_summaries(self) -> list[DomainSummary]:
    # Gathers count and size_bytes per domain in parallel
```

`get_total_size_bytes()` remains as a convenience aggregate but the API route derives `total_size_bytes` from per-domain sizes in summaries.

### 3. `GET /api/v0/data/domains`

```python
class DataDomainItem(BaseModel):
    name: str
    importable: bool
    count: int | None
    size_bytes: int

class DataDomainsResponse(BaseModel):
    domains: list[DataDomainItem]
    schema_revisions: list[str]
    total_records: int
    total_size_bytes: int
```

### 4. Web layout — two-column (matches Costs page)

Full-width `px-6 py-8` container with `grid grid-cols-[5fr_7fr]`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ DATA · Your data                                                         │
│                                                                          │
│  ┌─────────────────────────┐  ┌────────────────────────────────────┐  │
│  │ 12.4 MB                 │  │ BY DOMAIN                          │  │
│  │ total storage           │  │                                    │  │
│  │                         │  │ Memory                             │  │
│  │     ╭──────╮            │  │ facts      ████████░░  4.2 MB  1.2k │  │
│  │    ╱  donut ╲  legend  │  │ episodes   ████░░░░░░  1.8 MB   432 │  │
│  │    ╲ chart  ╱           │  │ …                                  │  │
│  │     ╰──────╯            │  │ Contacts                           │  │
│  │                         │  │ persons    ██░░░░░░░░  0.4 MB    38 │  │
│  │ ┌────┐ ┌────┐ ┌────┐   │  │ …                                  │  │
│  │ │ 42 │ │12k │ │Mem │   │  └────────────────────────────────────┘  │
│  │ │dom │ │rec │ │34% │   │                                          │
│  │ └────┘ └────┘ └────┘   │                                          │
│  └─────────────────────────┘                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Left column**
- Hero: total storage (`total_size_bytes`) in large type (same scale as Costs hero).
- Donut chart: storage grouped by domain prefix (`memory`, `contacts`, `goals`, …). Segments below 2% of total roll into **Other**. Legend shows label, formatted size, and percentage.
- Secondary stat cards: domain count, total records, largest category name + share.

**Right column** (scrollable)
- Domains grouped by prefix header.
- Each row: short name, horizontal size bar (% of total storage), formatted size, record count.
- `importable` pill when applicable.

Pure SVG for the donut — no chart library dependency (same approach as `SpendChart` on Costs).

### 5. Format helpers

`widgets/data-overview/lib/format.ts` — `formatBytes`, `domainPrefix`, `shortDomainName`.

---

## Module Locations

| Change | File |
|--------|------|
| `DataDomain.count` / `size_bytes` | `core/ze-data/ze_data/domain.py` |
| `DomainSummary`, `list_domain_summaries()` | `core/ze-data/ze_data/portability/service.py` |
| `DataDomainItem`, `DataDomainsResponse` | `apps/ze-api/ze_api/api/schemas.py` |
| `GET /api/v0/data/domains` | `apps/ze-api/ze_api/api/routes/data.py` |
| `_count` / `_size` wiring | Each plugin's `data_domains()` method |
| `useDataDomainsQuery` | `apps/ze-web/src/entities/data-domain/api/useDataDomainsQuery.ts` |
| `DataOverview` + chart + format lib | `apps/ze-web/src/widgets/data-overview/` |
| `DataPage` | `apps/ze-web/src/pages/data/ui/DataPage.tsx` |
| Nav + router | `shared/config/nav-routes.ts`, `app/router/routes.tsx` |

---

## Open Questions

- [x] Should `total_records` exclude domains with `count=None`? **Yes** — sum only known counts.
- [x] Chart granularity: per-domain or per-prefix? **Per-prefix** — too many domains for a readable donut; per-domain bars on the right.
- [x] Domains without `size_bytes`? **Contribute 0** to totals and are omitted from chart segments.
