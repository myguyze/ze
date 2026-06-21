# API Client Codegen — Spec

> **Package:** `packages/ze-client` (npm) · `ze_api/api/schemas.py` (Python)
> **Phase:** 72
> **Status:** Pending

---

## Implementation Status

| Feature | Status |
|---------|--------|
| Pydantic WS frame models in `schemas.py` | 🔲 Pending |
| `GET /api/ws-schema` endpoint | 🔲 Pending |
| `packages/ze-client/` scaffold + `package.json` | 🔲 Pending |
| `generate` script (REST + WS codegen) | 🔲 Pending |
| Generated REST types (`openapi-typescript`) | 🔲 Pending |
| Generated WS types (`json-schema-to-typescript`) | 🔲 Pending |
| `ze-web` migrated to `@ze/client` imports | 🔲 Pending |
| `Makefile` target `make codegen` | 🔲 Pending |

---

## Purpose

The frontend currently maintains hand-written TypeScript types that mirror the
Python backend's REST schemas (`types/api.ts`) and WebSocket protocol
(`features/websocket/protocol.ts`). These drift silently as the backend evolves.

This phase generates both the REST client types and the WebSocket frame types
automatically from the Python source, packages them as a local npm package
(`@ze/client`), and wires the web app to import from it — eliminating the
hand-maintained copies.

---

## Responsibilities

- Add Pydantic discriminated-union models for all WebSocket frame types to
  `ze_api/api/schemas.py` (Python is the source of truth for the WS protocol)
- Expose `GET /api/ws-schema` that returns the JSON Schema for those models
- Scaffold `packages/ze-client/` as an npm workspace package
- Implement a `generate` script that hits the running backend, runs
  `openapi-typescript` for REST and `json-schema-to-typescript` for WS, and
  writes the output into `src/generated/`
- Export a typed `createRestClient(config)` helper from `@ze/client` wrapping
  `openapi-fetch`
- Export a typed `WsInboundFrame` / `WsOutboundFrame` union from `@ze/client`
- Implement `blob.ts` in `@ze/client` with `downloadExport`, `importArchive`,
  and `healthCheck` (hand-written, not generated — multipart/blob operations)
- Remove `ze-web`'s hand-written duplicates (`lib/api.ts`, `types/api.ts`,
  `features/websocket/protocol.ts`) and replace with imports from `@ze/client`
- Add `make codegen` to the root `Makefile`

---

## Out of Scope

- WebSocket connection management (stays in `ze-web`'s `useWebSocket.ts`)
- React hooks or query-layer wrappers (not generated; kept in `ze-web`)
- Publishing `@ze/client` to a registry (local workspace only)
- Streaming / SSE — not used in this project; all WS frames are discrete JSON

---

## Module Location

```
packages/
└── ze-client/
    ├── package.json          # name: "@ze/client", private: true
    ├── tsconfig.json
    └── src/
        ├── index.ts          # re-exports everything below
        ├── rest.ts           # createRestClient(config) using openapi-fetch
        ├── ws.ts             # re-exports generated WS types
        ├── blob.ts           # hand-written helpers: downloadExport, importArchive, healthCheck
        └── generated/        # committed — written by codegen script
            ├── api.ts        # openapi-typescript output
            └── ws.ts         # json-schema-to-typescript output

scripts/
└── codegen.ts                # codegen entrypoint (bun run) — root scripts dir
```

Python changes:

```
ze_api/api/
├── schemas.py    # existing — add WS Pydantic models here
└── routes/
    └── ws_schema.py   # new — GET /api/ws-schema route
```

---

## Interface Contract

### REST client (`@ze/client`)

```typescript
import { createRestClient } from "@ze/client";

const client = createRestClient({ serverUrl: "http://localhost:8000", apiKey: "..." });

// Fully typed — path, method, params, and response inferred from OpenAPI spec
const contacts = await client.GET("/api/contacts");
const { data, error } = contacts;
```

`createRestClient` returns an `openapi-fetch` client typed against the generated
`paths` interface from `src/generated/api.ts`.

### WebSocket types (`@ze/client`)

```typescript
import type { WsInboundFrame, WsOutboundFrame } from "@ze/client";

// Type-safe send
function send(ws: WebSocket, frame: WsOutboundFrame) {
  ws.send(JSON.stringify(frame));
}

// Type-safe receive
function onMessage(raw: unknown): WsInboundFrame {
  return raw as WsInboundFrame; // narrowing via discriminant `type`
}
```

### Python: WS schema endpoint

```
GET /api/ws-schema
Authorization: Bearer <api-key>

Response 200:
{
  "inbound":  { ... JSON Schema for WsInboundFrame union ... },
  "outbound": { ... JSON Schema for WsOutboundFrame union ... }
}
```

### `generate` script

```bash
bun run scripts/codegen.ts \
  --server http://localhost:8000 \
  --api-key <key>
```

Writes `packages/ze-client/src/generated/api.ts` and `ws.ts`. Idempotent.

---

## Data Structures

### Python — WS frame Pydantic models (`ze_api/api/schemas.py`)

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

# ── Server → Client ──────────────────────────────────────────────────────────

class MessageFrame(BaseModel):
    type: Literal["message"]
    message: MessageSchema          # existing schema
    onboarding: OnboardingMeta | None = None

class EditFrame(BaseModel):
    type: Literal["edit"]
    id: str
    text: str | None = None
    components: list[dict] = []

class ConfirmRequestFrame(BaseModel):
    type: Literal["confirm_request"]
    id: str
    prompt: str
    actions: list[ConfirmAction]

class ConfirmCancelFrame(BaseModel):
    type: Literal["confirm_cancel"]
    id: str

class TypingFrame(BaseModel):
    type: Literal["typing"]
    text: str | None = None

class TokenFrame(BaseModel):
    type: Literal["token"]
    text: str

class ErrorFrame(BaseModel):
    type: Literal["error"]
    detail: str

class RefreshFrame(BaseModel):
    type: Literal["refresh"]
    screen: str

class PongFrame(BaseModel):
    type: Literal["pong"]

WsInboundFrame = Annotated[
    Union[
        MessageFrame, EditFrame, ConfirmRequestFrame, ConfirmCancelFrame,
        TypingFrame, TokenFrame, ErrorFrame, RefreshFrame, PongFrame,
    ],
    Field(discriminator="type"),
]

# ── Client → Server ──────────────────────────────────────────────────────────

class SendMessageFrame(BaseModel):
    type: Literal["message"]
    text: str
    thread_id: str | None = None
    context: ScreenContext | None = None

class AckFrame(BaseModel):
    type: Literal["ack"]
    ids: list[str]

class ConfirmFrame(BaseModel):
    type: Literal["confirm"]
    id: str
    choice: Literal["approve", "deny"]

class CommandFrame(BaseModel):
    type: Literal["command"]
    name: Literal["cancel", "costs", "capabilities", "status", "onboarding", "reset", "reset_preview"]

class ComponentSubmitFrame(BaseModel):
    type: Literal["component_submit"]
    step_id: str
    values: dict
    session_id: str | None = None
    thread_id: str | None = None

class PingFrame(BaseModel):
    type: Literal["ping"]

WsOutboundFrame = Annotated[
    Union[
        SendMessageFrame, AckFrame, ConfirmFrame,
        CommandFrame, ComponentSubmitFrame, PingFrame,
    ],
    Field(discriminator="type"),
]
```

---

## Configuration

No new config keys. The `generate` script reads `--server` and `--api-key` from
CLI args or environment variables `ZE_SERVER_URL` / `ZE_API_KEY`.

---

## Codegen pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│  make codegen                                                   │
│                                                                 │
│  1. bun run scripts/codegen.ts                                  │
│     ├── GET {server}/openapi.json                               │
│     │   └── openapi-typescript                                  │
│     │       → packages/ze-client/src/generated/api.ts          │
│     └── GET {server}/api/ws-schema                             │
│         └── json-schema-to-typescript                          │
│             → packages/ze-client/src/generated/ws.ts           │
│                                                                 │
│  2. ze-web imports @ze/client (workspace resolution)           │
└─────────────────────────────────────────────────────────────────┘
```

`packages/ze-client/` is added to the bun workspace in the root
`package.json`. `ze-web` adds `"@ze/client": "workspace:*"` to its
`package.json` and the build resolves it locally.

---

## Dependencies

| Dependency | Where | Purpose |
|------------|-------|---------|
| `openapi-typescript` | `ze-client` devDep | Generate types from OpenAPI spec |
| `openapi-fetch` | `ze-client` dep | Runtime typed fetch wrapper |
| `json-schema-to-typescript` | `ze-client` devDep | Generate WS types from JSON Schema |
| `pydantic` | `ze-api` (already present in `schemas.py`) | WS frame models + JSON Schema export |

---

## Migration: ze-web changes

| File | Action |
|------|--------|
| `src/lib/api.ts` | Delete — replaced by `createRestClient` from `@ze/client` |
| `src/types/api.ts` | Delete — types come from generated `api.ts` |
| `src/features/websocket/protocol.ts` | Delete — replaced by `WsInboundFrame`/`WsOutboundFrame` from `@ze/client` |
| `src/features/websocket/useWebSocket.ts` | Update imports only |
| `src/pages/*.tsx` | Update imports only |

All call sites switch from `api.get<T>(path)` to `client.GET(path)` with
inferred types. The runtime behaviour is identical — `openapi-fetch` wraps
`fetch` the same way.

`downloadExport`, `importArchive`, and `healthCheck` move verbatim from
`lib/api.ts` into `@ze/client/blob.ts`. They are hand-written (not generated)
because they deal with multipart upload and blob download, which `openapi-fetch`
does not handle ergonomically. They are exported from `@ze/client`'s index so
`ze-web` has a single import point for the entire API surface.

---

## Implementation Notes

- `src/generated/` is committed. `make codegen` regenerates it; CI fails if
  the committed files are stale (run codegen in CI and `git diff --exit-code`).
- The `GET /api/ws-schema` endpoint uses `WsInboundFrame.__get_pydantic_core_schema__`
  / `model_json_schema(mode="serialization")` to export separate schemas for
  inbound and outbound unions.
- The Pydantic WS models in `schemas.py` are **not** used at runtime for
  parsing incoming WS frames — the endpoint dispatch logic (`endpoint.py`)
  remains a plain `data.get("type")` switch. The models exist solely as the
  canonical schema definition for codegen.
- `openapi-fetch` is zero-overhead: it is just a thin TypeScript wrapper around
  native `fetch` with no runtime type enforcement.

---

## Open Questions

- [x] Should `src/generated/` be committed or gitignored? → **Committed.**
  CI regenerates and fails on diff.
- [x] Should blob helpers (`downloadExport`, `importArchive`, `healthCheck`)
  live in `ze-web` or `@ze/client`? → **In `@ze/client`** (`blob.ts`).
  The full API surface belongs in the managed package.
