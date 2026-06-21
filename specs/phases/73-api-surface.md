# API Surface — Spec

> **Package:** `ze_api` · `packages/ze-client`
> **Phase:** 73
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| All routes under `/api/v0/` prefix | ✅ Done |
| `HTTPBearer` security scheme on all protected routes | ✅ Done |
| Explicit `operation_id` on every route | ✅ Done |
| Duplicate and legacy routes removed | ✅ Done |
| Auth extracted into `require_api_key` Depends (no raw `Header()` in signatures) | ✅ Done |
| `@ze/client` version `0.1.0` pinned to API `v0` | ✅ Done |
| `GET /api/v0/version` endpoint (public) | ✅ Done |
| Codegen produces clean named SDK methods | ✅ Done |
| Tests updated for new paths + auth override | ✅ Done |

---

## Purpose

Ze's REST API is inconsistent: routes lack a uniform prefix, authentication leaks
into the OpenAPI param list, operationIds are auto-generated garbage, and two
duplicate cost endpoints coexist. This makes typed client generation produce
unreadable names and makes the spec untrustworthy as a contract.

This phase establishes a versioned, uniform API surface — every route under
`/api/v0/`, every operationId explicit and camelCase, auth declared as a security
scheme — so that `@ze/client` vv0.x generates clean named methods with zero route
strings visible to callers.

The client package version is coupled to the API version: `@ze/client@0.x.y`
speaks `/api/v0/`. A future `/api/v1/` bump ships as `@ze/client@1.x.y`.

---

## Responsibilities

- Move all routes to `/api/v0/` (replace the current mix of bare paths and `/api/` paths)
- Declare `HTTPBearer` as the security scheme at app level; apply to all protected routes
- Add an explicit `operation_id` (camelCase) to every route decorator
- Extract the bearer-key check into a reusable FastAPI `Depends` (`require_api_key`)
- Remove the legacy `/costs/summary` route (superseded by `/api/v0/costs/summary`)
- Remove the bare `/capabilities`, `/memory`, `/routing`, `/workflows` prefixes
- Add `GET /api/v0/version` returning `{ api_version: "v0", client_version: "0.1.0" }`
- Set `@ze/client` package version to `0.x.y`; document the coupling in `CLAUDE.md`
- Update ze-web and any other callers to the new paths

---

## Out of Scope

- GraphQL (decided against — see spec notes)
- Breaking changes to the WebSocket protocol (separate from REST)
- Pagination on list endpoints (deferred)
- Rate limiting, CORS policy changes
- `/eval/` routes — keep as-is (internal tooling, not part of the public surface)

---

## Route Map

Every route moves to `/api/v0/`. The right column is the new path and its
`operation_id`.

### Core chat / messages

| Old path | New path | operationId |
|---|---|---|
| `GET /api/messages` | `GET /api/v0/messages` | `listMessages` |
| `GET /api/sessions` | `GET /api/v0/sessions` | `listSessions` |
| `POST /api/sessions` | `POST /api/v0/sessions` | `createSession` |
| `GET /api/health` | `GET /api/v0/health` | `healthCheck` |
| `GET /api/ws-schema` | `GET /api/v0/ws-schema` | `getWsSchema` |

### Personal data screens

| Old path | New path | operationId |
|---|---|---|
| `GET /api/contacts` | `GET /api/v0/contacts` | `listContacts` |
| `GET /api/goals` | `GET /api/v0/goals` | `listGoals` |
| `GET /api/reminders` | `GET /api/v0/reminders` | `listReminders` |
| `GET /api/news` | `GET /api/v0/news` | `listNews` |
| `GET /api/costs/summary` | `GET /api/v0/costs/summary` | `getCostSummary` |
| `GET /costs/summary` | **deleted** (duplicate) | — |

### Memory

| Old path | New path | operationId |
|---|---|---|
| `GET /memory/facts` | `GET /api/v0/memory/facts` | `listFacts` |
| `POST /memory/facts/review` | `POST /api/v0/memory/facts/review` | `reviewFacts` |
| `GET /memory/digest` | `GET /api/v0/memory/digest` | `getMemoryDigest` |
| `POST /memory/consolidate` | `POST /api/v0/memory/consolidate` | `consolidateMemory` |
| `GET /memory/profile` | `GET /api/v0/memory/profile` | `getProfile` |

### Capabilities

| Old path | New path | operationId |
|---|---|---|
| `GET /capabilities` | `GET /api/v0/capabilities` | `listCapabilities` |
| `PUT /capabilities/{agent}/{intent}` | `PUT /api/v0/capabilities/{agent}/{intent}` | `updateCapability` |

### Workflows

| Old path | New path | operationId |
|---|---|---|
| `GET /workflows` | `GET /api/v0/workflows` | `listWorkflows` |
| `GET /workflows/{id}` | `GET /api/v0/workflows/{id}` | `getWorkflow` |
| `GET /workflows/{id}/executions` | `GET /api/v0/workflows/{id}/executions` | `listWorkflowExecutions` |
| `POST /workflows/{id}/trigger` | `POST /api/v0/workflows/{id}/trigger` | `triggerWorkflow` |

### Data portability

| Old path | New path | operationId |
|---|---|---|
| `GET /api/data/export` | `GET /api/v0/data/export` | `exportData` |
| `POST /api/data/import` | `POST /api/v0/data/import` | `importData` |
| `POST /api/data/delete-intent` | `POST /api/v0/data/delete-intent` | `createDeleteIntent` |
| `DELETE /api/data` | `DELETE /api/v0/data` | `deleteData` |

### Routing log

| Old path | New path | operationId |
|---|---|---|
| `GET /routing/log` | `GET /api/v0/routing/log` | `getRoutingLog` |

### Ingest

| Old path | New path | operationId |
|---|---|---|
| `POST /api/ingest` | `POST /api/v0/ingest` | `ingest` |

---

## Interface Contract

### Version endpoint

```
GET /api/v0/version
(no auth required)

200: { "api_version": "v0", "client_version": "0.1.0" }
```

`client_version` matches the `version` field in `packages/ze-client/package.json`.
The version endpoint is the canonical way for a client to detect protocol skew.

### Auth

All routes except `/api/v0/health` and `/api/v0/version` require:

```
Authorization: Bearer <ZE_API_KEY>
```

The OpenAPI spec declares this as a `http` security scheme with `bearerFormat: "apiKey"`:

```python
# ze_api/api/app.py
app = FastAPI(
    ...
    openapi_components={
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "ApiKey",
            }
        }
    },
)
```

Each protected route carries `security=[{"bearerAuth": []}]`. With this, the generated
client automatically sets the `Authorization` header — auth is not a param.

### Auth dependency

```python
# ze_api/api/dependencies.py
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)

async def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    expected = request.app.state.settings.ze_api_key
    token = credentials.credentials if credentials else ""
    if token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
```

All routes that previously called `_verify_bearer_api_key(request, authorization)` inline
switch to `Depends(require_api_key)`.

### Version / client coupling

```
API version    @ze/client version    Breaking?
v0             0.x.y                 no  — additive changes only; minor + patch bump
v1             1.x.y                 yes — routes renamed/removed; major bump
```

`packages/ze-client/package.json`:
```json
{
  "name": "@ze/client",
  "version": "0.1.0"
}
```

When the API graduates to v1, the package bumps to `1.0.0` and the old `0.x.y` is
yanked (Ze is single-user; no multi-version support needed).

---

## Implementation Notes

- The WS endpoint stays at `/ws` — it is not versioned (the WS protocol is
  versioned separately via the `GET /api/v0/ws-schema` codegen contract).
- The `/eval/` routes are internal tooling; they are exempt from the versioning
  contract and keep their current paths.
- FastAPI's `include_router` `prefix` arg is the right place to add `/api/v0` —
  not in individual route decorators. One prefix change per router covers all routes.
- Old paths are removed immediately — no 410 shims. Ze is single-user with no
  external API consumers; a hard cut is safe and keeps the codebase clean.

---

## Open Questions

- [x] Should `GET /api/v0/health` remain unauthenticated? → **Yes.** Needed before
  credentials are configured (settings page connection test).
- [x] Should `/api/v0/version` be unauthenticated? → **Yes.** Same reason — version
  checking is a pre-auth operation.
- [x] Should `GET /api/v0/ws-schema` be authenticated? → **Yes.** Dev/codegen only,
  not an end-user endpoint.
