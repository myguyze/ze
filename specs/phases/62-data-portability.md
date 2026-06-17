# Phase 62 — Data Portability (Export & Deletion)

> **Status:** Done
> **Depends on:** Phase 49 (ze-sdk), Phase 46 (accountability / confirmation flow), Phase 20 (ZePlugin)

---

## Problem

Ze accumulates a large corpus of personal data — memories, goals, contacts, emails
metadata, calendar reminders, usage telemetry, persona settings — but provides no way
for the user to get that data out, or to wipe it. For a single-user personal assistant
that handles sensitive life data, export and deletion must be first-class features, not
afterthoughts.

---

## Goals

1. **Export**: one REST call produces a portable ZIP archive of all user data as
   structured JSON files, one per domain. No data is lost or flattened.
2. **Delete**: one confirmed REST call hard-deletes every row of user data across all
   tables, resetting Ze to a blank-slate state. Requires explicit double-confirmation.
3. **Web UI only**: Export and Delete are available exclusively on a Settings page in
   the web UI. No agent or chat command can trigger either operation.
4. **Plugin-extensible**: each ZePlugin declares what tables it owns via a new
   `data_domains()` hook; the export/delete engine calls each plugin in topological
   order.

---

## Out of Scope

- Triggering export or deletion via chat / agent commands — Settings UI only.
- Selective export (e.g., "only export my contacts") — full archive only for now.
- GDPR Article 20 machine-readable portability to another service.
- Exporting raw email bodies or calendar event payloads fetched from Google — Ze only
  stores derived metadata; the originals live in Google.
- Encrypted export archives — the archive is plaintext JSON; transport security is
  HTTPS.
- Partial deletion (e.g., "delete only my goals") — full wipe only.
- Account deactivation / soft-delete — this is a hard delete.

---

## Architecture

```
Web UI Settings page
        │
        ├── Export button → GET /data/export → ZIP download
        │
        └── Delete button → modal (type "DELETE" to confirm)
                                │
                                ▼
                    POST /data/delete-intent → token
                                │
                                ▼
                    DELETE /data (token) → 204
                                │
                                ▼
                    DataPortabilityService
                      export()  → ExportArchive
                      delete()  → void
                                │
                                ▼
                    ZePlugin.data_domains()  (×N)
                      → DataDomain(name, exporter_fn, deleter_fn)
                                │
                                ▼
                    ExportAssembler           DeleteOrchestrator
                      runs each exporter_fn     runs each deleter_fn in dep order
                      writes JSON to ZIP        commits after all succeed
```

---

## Plugin Hook: `data_domains()`

```python
# core/ze-agents/ze_agents/plugin.py

@dataclass
class DataDomain:
    name: str                             # e.g. "memory.facts"
    export: Callable[[DBPool], Awaitable[list[dict]]]
    delete: Callable[[DBPool], Awaitable[None]]
    # delete_order: lower = deleted first (leaf tables before referenced tables)
    delete_order: int = 50

class ZePlugin:
    def data_domains(self) -> list[DataDomain]:
        return []
```

Each plugin implementing this hook is responsible for:
- Exporting all rows it owns as a list of plain dicts (JSON-serialisable).
- Deleting all rows it owns, respecting FK ordering via `delete_order`.

The engine never reads plugin table names directly — it delegates entirely to the
plugin's own functions.

---

## Data Domains per Plugin

### `ze-personal` (delete_order 10–40)

| Domain name | Table(s) | delete_order |
|---|---|---|
| `memory.facts` | `memory_facts` | 10 |
| `memory.episodes` | `memory_episodes` | 10 |
| `memory.portrait` | `user_portrait` | 10 |
| `memory.insights` | `insights` | 10 |
| `contacts.persons` | `persons` | 20 |
| `contacts.channels` | `contact_channels` | 15 |
| `goals.goals` | `goals` | 30 |
| `goals.milestones` | `goal_milestones` | 35 |
| `goals.traces` | `goal_execution_traces` | 35 |
| `goals.retrospectives` | `goal_retrospectives` | 35 |
| `workflow.workflows` | `workflows` | 30 |
| `workflow.steps` | `workflow_steps` | 35 |
| `persona.overrides` | `persona_overrides` | 10 |

### `ze-calendar` (delete_order 10)

| Domain name | Table(s) | delete_order |
|---|---|---|
| `calendar.reminders` | `reminders` | 10 |

### `ze-prospecting` (delete_order 10–20)

| Domain name | Table(s) | delete_order |
|---|---|---|
| `prospecting.campaigns` | `prospect_campaigns` | 10 |
| `prospecting.targets` | `prospect_targets` | 15 |

### `ze-core` (engine-owned, handled by `ze-api` container)

| Domain name | Table(s) | delete_order |
|---|---|---|
| `telemetry.costs` | `cost_log`, `cost_reconciliation` | 10 |
| `telemetry.capabilities` | `capability_overrides` | 10 |
| `routing.embeddings` | `agent_routing_store` | 10 |
| `messages.store` | `messages` | 10 |
| `confirmations` | `confirmation_requests` | 10 |
| `proactive.log` | `push_log` | 10 |
| `graph.checkpoints` | LangGraph checkpoint tables | 50 |

LangGraph checkpoint tables are deleted last (order 50) because they reference no Ze
tables and there is no point replaying them after all domain data is gone.

---

## Export Archive Format

```
ze-export-<ISO8601>.zip
├── manifest.json          # { "ze_version": "...", "exported_at": "...", "domains": [...] }
├── memory.facts.json      # [ { "id": "...", "content": "...", ... }, ... ]
├── memory.episodes.json
├── memory.portrait.json
├── contacts.persons.json
├── goals.goals.json
├── goals.milestones.json
├── ...
└── graph.checkpoints.json # raw checkpoint rows; opaque but included for completeness
```

- Each `*.json` file is a JSON array of objects, one per row.
- Column names are the raw database column names (snake_case).
- `TIMESTAMPTZ` values serialised as ISO 8601 strings.
- Binary / bytea columns (e.g. embedding vectors) serialised as base64.

---

## REST API

### `GET /data/export`

Streams a ZIP archive to the client.

```
Response: 200 application/zip
Content-Disposition: attachment; filename="ze-export-<ISO8601>.zip"
```

No request body. Authenticated via `ZE_API_KEY` header (same as all routes).

Generation is synchronous — the endpoint awaits all exporters before streaming.
For the expected data volumes (single user) this is fine; no background job needed.

### `DELETE /data`

Hard-deletes all user data.

```
Request body: { "confirmation_token": "<UUID>" }
Response: 204 No Content
```

The `confirmation_token` must have been issued by `POST /data/delete-intent` within the
last 10 minutes. This is a second-factor check distinct from the chat confirmation flow.

### `POST /data/delete-intent`

Issues a short-lived token that gates `DELETE /data`.

```
Response: { "confirmation_token": "<UUID>", "expires_at": "<ISO8601>" }
```

The client must display a warning, have the user acknowledge, and then call
`DELETE /data` with the token. The web UI handles this flow; the chat agent calls both
endpoints internally after the graph confirmation step.

---

## Module Location

```
core/ze-agents/ze_agents/
  plugin.py           ← add DataDomain dataclass + data_domains() hook

apps/ze-api/ze_api/
  data/
    __init__.py
    service.py        ← DataPortabilityService (export + delete orchestration)
    assembler.py      ← ExportAssembler (ZIP builder)
    routes.py         ← FastAPI routes: GET /data/export, POST /data/delete-intent, DELETE /data
    types.py          ← DataDomain (re-exported from ze-agents), ExportManifest
```

---

## Web UI

New **Settings** page (tab in the side nav):

- **Export your data** — primary button → calls `GET /data/export` → browser download.
- **Delete all data** — destructive button (outlined red) → opens a confirmation modal.

### Deletion modal — UX requirements

The modal must make clear that this action is permanent before the user can proceed.
It flows in this order:

1. **Headline**: "Delete all data?" in large text.
2. **Impact summary**: a brief list of what will be erased — memories, goals, contacts,
   messages, reminders, usage history. No room for ambiguity about scope.
3. **Irreversibility statement**: explicit sentence that this cannot be undone.
4. **Export nudge**: a secondary action ("Export your data first") so the user can
   download a copy without dismissing the modal. Clicking it triggers the same export
   as the Settings page button and keeps the modal open.
5. **Challenge input**: labelled `Type DELETE to confirm`. The confirm button remains
   disabled until the field contains exactly `DELETE` (case-sensitive). This is the
   proof-of-intent gate — it requires deliberate typed action, not just clicking through.
6. **Confirm button**: labelled "Delete everything", styled destructive red, enabled
   only when the challenge passes.
7. **On success**: modal closes, local config is cleared, page reloads to the empty
   onboarding / chat screen.

The challenge is intentionally lightweight (typed phrase, no second credential required)
because Ze is a single-user, self-hosted system where the API key is already embedded in
the client. The `DELETE` phrase is long enough to prevent accidental confirmation but
short enough not to be frustrating.

---

## Implementation Notes

- `DELETE /data` must run all deleters in a single transaction where possible. For tables
  outside a single Postgres schema (e.g. if LangGraph uses its own schema), delete them
  in a separate step after the main transaction commits.
- LangGraph checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`)
  are managed by `langgraph-checkpoint-postgres` — use `AsyncPostgresSaver.adelete()`
  or raw `DELETE FROM` if the library provides no bulk-delete API.
- Export is read-only and does not need a transaction; run all exporters concurrently
  with `asyncio.gather`.
- The `confirmation_token` for `DELETE /data` is a UUID stored in-process (dict keyed
  by token, value = expiry). No DB table needed — the server restarts clear all pending
  tokens, which is acceptable given the 10-minute window.
- Do not log the deletion event to `cost_log` after the deletion — the table will be
  empty. Log it to the server log file only.

---

## Open Questions

- [ ] Should the export include the raw LangGraph checkpoint blob bytes, or skip them as
      opaque/unreadable? (Current proposal: include as base64 for completeness.)
- [ ] Should `DELETE /data` also revoke the Google OAuth2 refresh token (i.e., disconnect
      Google Calendar / Gmail access)?
- [ ] Is a "delete only conversation history" partial wipe worth adding as a fast-follow?
