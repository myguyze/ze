# Phase 62 — Data Portability (Export, Import & Deletion)

> **Status:** Done
> **Depends on:** Phase 49 (ze-sdk), Phase 46 (accountability / confirmation flow), Phase 20 (ZePlugin)

---

## Problem

Ze accumulates a large corpus of personal data — memories, goals, contacts, emails
metadata, calendar reminders, usage telemetry, persona settings — but provides no way
for the user to get that data out, move it to another instance, or wipe it. For a
single-user personal assistant that handles sensitive life data, export, import, and
deletion must be first-class features, not afterthoughts.

---

## Goals

1. **Export**: one REST call produces a versioned ZIP archive of all user data as
   structured JSON files, one per domain. No data is lost or flattened.
2. **Import**: one REST call restores a previously exported archive into an empty Ze
   instance. The archive must match the current schema revision; the instance must be
   empty.
3. **Delete**: one confirmed REST call hard-deletes every row of user data across all
   tables, resetting Ze to a blank-slate state. Requires typed-phrase confirmation.
4. **Web UI only**: Export, Import, and Delete are available exclusively on the Settings
   page. No agent or chat command can trigger any of these operations.
5. **Plugin-extensible**: each ZePlugin declares what tables it owns via a `data_domains()`
   hook; the export/import/delete engine calls each plugin in the correct order.

---

## Out of Scope

- Triggering export, import, or deletion via chat / agent commands — Settings UI only.
- Selective export (e.g., "only export my contacts") — full archive only.
- GDPR Article 20 machine-readable portability to another service.
- Exporting raw email bodies or calendar event payloads fetched from Google — Ze only
  stores derived metadata; the originals live in Google.
- Encrypted export archives — the archive is plaintext JSON; transport security is HTTPS.
- Partial deletion (e.g., "delete only my goals") — full wipe only.
- Account deactivation / soft-delete — this is a hard delete.
- Merge import (importing into a non-empty instance) — clean import only.
- Schema migration of older archives — archives must match the running schema exactly.

---

## Architecture

```
Web UI Settings page
        │
        ├── Export button → GET /api/data/export → ZIP download
        │
        ├── Import button → file picker → POST /api/data/import (multipart ZIP)
        │                                   │
        │                               manifest check (schema_revisions)
        │                               empty-instance check
        │                               import domains in reverse delete_order
        │
        └── Delete button → modal (type "DELETE" + export nudge)
                                │
                                ▼
                    POST /api/data/delete-intent → token
                                │
                                ▼
                    DELETE /api/data (token) → 204

All three paths flow through DataPortabilityService, which iterates
ZePlugin.data_domains() and the engine-owned domains in the correct order.
```

---

## Versioning

Every export archive embeds the current Alembic heads at the time of export in
`manifest.json`. These heads are read directly from the `alembic_version` Postgres
table — they represent what schema is actually running, not what the code declares.

```json
{
  "exported_at": "2026-06-17T15:00:00Z",
  "schema_revisions": ["011", "zc010", "zc009"],
  "domains": ["memory.facts", "memory.episodes", "..."]
}
```

At import time, `DataPortabilityService` compares the archive's `schema_revisions` set
against the current `alembic_version` rows. If they differ:

- **Archive older than running schema**: refuse with a clear message. The user should
  export from the Ze instance that created the archive, upgrade that instance, and
  re-export, or accept data loss.
- **Archive newer than running schema**: refuse. The user must upgrade Ze before
  importing.
- **Exact match**: proceed.

This is a strict equality check. No partial compatibility, no automatic migration of
archive data. The invariant is: if the schemas match, the raw row format in the archive
is directly insertable without transformation beyond datetime string parsing.

---

## Plugin Hook: `data_domains()`

```python
# core/ze-agents/ze_agents/plugin.py

@dataclass
class DataDomain:
    name: str                                          # e.g. "memory.facts"
    export: Callable[[DBPool], Awaitable[list[dict]]]
    delete: Callable[[DBPool], Awaitable[None]]
    # lower = deleted first (leaf tables before referenced tables)
    delete_order: int = 50
    # None = domain is not importable (e.g. opaque checkpoint blobs)
    importer: Callable[[DBPool, list[dict]], Awaitable[int]] | None = None

class ZePlugin:
    def data_domains(self) -> list[DataDomain]:
        return []
```

Import order is the reverse of delete order: domains with higher `delete_order` are
imported first (parents before children), so FK constraints are satisfied.

Each plugin is responsible for:
- **Exporting** all rows it owns as a list of plain dicts.
- **Deleting** all rows it owns in FK-safe order via `delete_order`.
- **Importing** rows from a deserialized JSON list back into the database.
  The importer receives rows with datetime strings already coerced to `datetime`
  objects by the import assembler.

---

## Data Domains per Plugin

### `ze-personal`

| Domain name | Table(s) | delete_order | importable |
|---|---|---|---|
| `memory.facts` | `user_facts` | 10 | ✅ |
| `memory.episodes` | `episodes` | 10 | ✅ |
| `memory.profile` | `user_profile` | 10 | ✅ |
| `memory.profile_facets` | `memory_profile_facets` | 10 | ✅ |
| `memory.entities` | `memory_entities` | 10 | ✅ |
| `memory.events` | `memory_events` | 10 | ✅ |
| `memory.procedures` | `memory_procedures` | 10 | ✅ |
| `memory.relationships` | `memory_relationships` | 10 | ✅ |
| `memory.task_state` | `memory_task_state` | 10 | ✅ |
| `memory.insights` | `insights` | 10 | ✅ |
| `persona.state` | `persona_state` | 10 | ✅ |
| `contacts.channels` | `contact_channels` | 20 | ✅ |
| `contacts.sources` | `contact_sources` | 20 | ✅ |
| `contacts.relationships` | `contact_relationships` | 20 | ✅ |
| `goals.milestones` | `goal_milestones` | 20 | ✅ |
| `goals.gates` | `goal_gates` | 20 | ✅ |
| `goals.learnings` | `goal_learnings` | 20 | ✅ |
| `goals.traces` | `goal_execution_traces` | 20 | ✅ |
| `goals.suggestions` | `goal_suggestions` | 20 | ✅ |
| `workflow.executions` | `workflow_executions` | 20 | ✅ |
| `contacts.persons` | `contacts` | 30 | ✅ |
| `goals.goals` | `goals` | 30 | ✅ |
| `workflow.workflows` | `workflows` | 30 | ✅ |

### `ze-calendar`

| Domain name | Table(s) | delete_order | importable |
|---|---|---|---|
| `calendar.reminders` | `user_reminders` | 10 | ✅ |
| `calendar.calendar_reminders` | `calendar_reminders` | 10 | ✅ |

### `ze-prospecting`

| Domain name | Table(s) | delete_order | importable |
|---|---|---|---|
| `prospecting.outreach` | `prospect_outreach` | 10 | ✅ |
| `prospecting.campaigns` | `prospect_campaigns` | 20 | ✅ |

### `ze-core` (engine-owned, declared in `ze_api/container.py`)

| Domain name | Table(s) | delete_order | importable |
|---|---|---|---|
| `telemetry.costs` | `llm_cost_log` | 10 | ✅ |
| `telemetry.anomalies` | `accountability_anomalies` | 10 | ✅ |
| `telemetry.capabilities` | `capability_overrides` | 10 | ✅ |
| `routing.log` | `routing_log` | 10 | ✅ |
| `messages.store` | `messages` | 10 | ✅ |
| `confirmations` | `pending_confirmations` | 10 | ✅ |
| `proactive.log` | `push_log` | 10 | ✅ |
| `sessions` | `sessions` | 10 | ✅ |
| `onboarding` | `onboarding_sessions`, `onboarding_steps`, `onboarding_seeds` | 10 | ✅ |
| `graph.checkpoints` | LangGraph checkpoint tables | 50 | ❌ |

LangGraph checkpoint tables contain opaque serialized graph state. They are exported for
completeness but not importable — a fresh Ze instance starts with no in-flight graphs,
which is the correct state after a restore.

---

## Archive Format

```
ze-export-<ISO8601>.zip
├── manifest.json          # versioning header + domain list (see Versioning section)
├── memory.facts.json      # [ { "id": "...", "content": "...", ... }, ... ]
├── memory.episodes.json
├── memory.profile.json
├── contacts.persons.json
├── goals.goals.json
├── goals.milestones.json
├── ...
└── graph.checkpoints.json # raw checkpoint rows; exported but not imported
```

- Each `*.json` file is a JSON array of objects, one per row.
- Column names are raw database column names (snake_case).
- `TIMESTAMPTZ` values serialised as ISO 8601 strings; parsed back to `datetime` on import.
- Float array columns (e.g. embedding vectors stored as `float[]`) serialise as JSON
  arrays of numbers and are directly re-insertable.
- `BYTEA` columns serialise as base64 strings. Only LangGraph blob columns use bytea;
  since those domains are not importable, no base64 decoding is needed during import.

---

## REST API

### `GET /api/data/export`

```
Response: 200 application/zip
Content-Disposition: attachment; filename="ze-export-<ISO8601>.zip"
```

Authenticated via `Authorization: Bearer <key>`. All exporters run concurrently.
Failures in individual exporters are logged and produce an empty array for that domain
rather than aborting the archive.

### `POST /api/data/import`

```
Request: multipart/form-data, field name "file", Content-Type application/zip
Response: 200 { "domains_imported": [...], "rows_imported": { "memory.facts": 42, ... } }
Errors:
  422 { "detail": "Schema mismatch: archive revisions [...] ≠ current [...]. ..." }
  409 { "detail": "Instance is not empty. Delete all data before importing." }
```

The endpoint:
1. Reads `manifest.json` from the uploaded ZIP.
2. Compares `schema_revisions` against the current `alembic_version` table.
3. Checks that all importable domain tables are empty.
4. Imports domains in descending `delete_order` (parents before children).
5. Returns the list of domains imported and row counts per domain.

Import runs in a single `asyncpg` transaction. On any error the transaction is rolled
back and the instance is left untouched.

### `POST /api/data/delete-intent`

```
Response: 201 { "confirmation_token": "<UUID>", "expires_at": "<ISO8601>" }
```

### `DELETE /api/data`

```
Request body: { "confirmation_token": "<UUID>" }
Response: 204 No Content
```

Token is valid for 10 minutes. Stored in-process (no DB table needed).

---

## Module Location

```
core/ze-agents/ze_agents/
  plugin.py           ← DataDomain (add importer field) + data_domains() hook

apps/ze-api/ze_api/
  data/
    __init__.py
    service.py        ← DataPortabilityService: export, import_archive, delete,
                         create_delete_intent, consume_delete_intent, is_empty,
                         get_schema_revisions
    assembler.py      ← ExportAssembler (ZIP build), ImportAssembler (ZIP parse + coerce)
    routes.py         ← GET /export, POST /import, POST /delete-intent, DELETE /
    types.py          ← ExportManifest, ImportResult
```

---

## Web UI

The Settings page has a **Your data** section with three actions in this order:

1. **Export your data** — downloads the ZIP archive.
2. **Import data** — opens a file picker (`.zip` only). After the user selects a file,
   Ze uploads it and shows a result summary (domains restored, row counts) or an error.
   If the instance is not empty, the error message directs the user to delete first.
3. **Delete all data** — opens a confirmation modal.

### Deletion modal — UX requirements

The modal must make clear that this action is permanent before the user can proceed.
It flows in this order:

1. **Headline**: "Delete all data?" in large text.
2. **Impact summary**: a brief list of what will be erased — memories, goals, contacts,
   messages, reminders, usage history.
3. **Irreversibility statement**: "This cannot be undone."
4. **Export nudge**: a secondary "Export your data first" button that triggers a download
   without closing the modal.
5. **Challenge input**: `Type DELETE to confirm`. The confirm button is disabled until the
   field contains exactly `DELETE` (case-sensitive).
6. **Confirm button**: "Delete everything", destructive red.
7. **On success**: config is cleared, page reloads to the empty state.

The `DELETE` phrase is the proof-of-intent gate — deliberate typed action, not accidental
click-through. No second credential is required because this is a self-hosted, single-user
instance where the API key is already embedded in the client.

---

## Implementation Notes

- `DELETE /api/data` runs all deleters in ascending `delete_order`. LangGraph checkpoint
  tables (order 50) are deleted last as a separate step since they may be in a different
  schema.
- `POST /api/data/import` runs all importers in **descending** `delete_order` so parents
  are inserted before children. The entire import runs inside one `asyncpg` transaction.
- The `_coerce_row` function in `assembler.py` heuristically parses ISO 8601 strings in
  row values to `datetime` objects (detected by the `YYYY-MM-DDTHH:MM:SS` prefix). This
  handles `TIMESTAMPTZ` columns without requiring column-type metadata in the archive.
  Float array / vector columns round-trip as JSON arrays naturally.
- `is_empty()` checks a representative set of tables (one per domain with `importer`
  set). If any table has rows, the instance is considered non-empty.
- `get_schema_revisions()` queries `SELECT version_num FROM alembic_version` via asyncpg
  and returns the result as a sorted list of strings.
- The `confirmation_token` for `DELETE /api/data` is a `dict[str, datetime]` stored
  in-process. Server restarts clear all pending tokens, which is acceptable given the
  10-minute window.

---

## Open Questions

- [x] Should `graph.checkpoints` be imported? **No** — opaque blobs, not importable.
- [ ] Should `DELETE /api/data` also revoke the Google OAuth2 refresh token?
- [ ] Is a "delete only conversation history" partial wipe worth a fast-follow?
