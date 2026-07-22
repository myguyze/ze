# packages/

Shared packages consumed across the monorepo. This directory holds:

- **Python** — `ze-sdk`, the plugin authoring surface (uv workspace member)
- **TypeScript** — `@ze/client` and `@ze/ui` (Bun workspace; consumed by `apps/ze-web`)

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-sdk](ze-sdk/) | Public Python SDK — flat re-export layer for plugin authors |
| [ze-client](ze-client/) | `@ze/client` — typed REST SDK and WebSocket frame types for `ze-api` |
| [ze-ui](ze-ui/) | `@ze/ui` — server-driven UI contract, runtime validation, and React renderer |

## ze-sdk

Plugin authors list `ze-sdk` as their only Ze dependency and import from `ze_sdk.*`.
It re-exports the stable surface from `ze-agents`, `ze-plugin`, `ze-proactive`,
`ze-memory`, `ze-communication`, and related core packages — never `ze-core` engine
internals. See [ze-sdk/README.md](ze-sdk/README.md) and [docs/sdk.md](../docs/sdk.md).

Tests: `make test-sdk`.

## @ze/client

Generated TypeScript surface for the entire `ze-api` REST and WebSocket protocol.
`ze-web` is the only consumer.

| Module | What it provides |
|--------|-----------------|
| `src/generated/sdk.gen.ts` | Named SDK functions from FastAPI `operation_id` values |
| `src/generated/types.gen.ts` | REST request/response types |
| `src/generated/ws.ts` | WebSocket frame types |
| `src/client.ts` | `configure()` / `createZeClient()` — default client wiring |
| `src/blob.ts` | `downloadExport`, `importArchive`, `healthCheck` |
| `src/error.ts` | `ApiError` |

```typescript
import { configure } from "@ze/client";
import { listContacts } from "@ze/client";

configure({ serverUrl, apiKey });
const { data } = await listContacts();
```

## @ze/ui

Canonical frontend contract for server-driven UI primitive trees emitted by
`ze-components` into WebSocket `components` frames.

| Export | What it provides |
|--------|-----------------|
| `@ze/ui` | `Primitive`, `parsePrimitiveTree`, `validatePrimitiveTree`, `PrimitiveValidationError` |
| `@ze/ui/react` | `PrimitiveRenderer`, `PrimitiveTreeRenderer`, action callbacks |

The contract layer is framework-neutral; the React renderer accepts already-parsed
trees and delegates transport (WebSocket sends, onboarding session state) to the
host app.

```typescript
import { parsePrimitiveTree } from "@ze/ui";
import { PrimitiveTreeRenderer } from "@ze/ui/react";

const nodes = parsePrimitiveTree(rawComponents);
<PrimitiveTreeRenderer nodes={nodes} actions={actions} />
```

## Code generation

Both TypeScript packages ship committed generated artifacts under `src/generated/`.
Regenerate after changing FastAPI routes, WebSocket schemas, or `ze-components`
primitive types:

```bash
make codegen
```

Sources of truth:

- `@ze/client` — OpenAPI spec (REST) and Pydantic WS frame models
- `@ze/ui` — `ze_components.schema.export_json_schema()`

## Testing

```bash
make test-sdk                   # ze-sdk (pytest)
cd packages/ze-ui && bun run test
cd apps/ze-web && bun run test
make test-web                   # vitest for TS packages + ze-web
```

## Where new code goes

| New code | Package |
|----------|---------|
| New plugin-facing re-export | `packages/ze-sdk` |
| New REST route types or SDK method | regenerate `@ze/client` via `make codegen` |
| New UI primitive type | `core/ze-components` + regenerate `@ze/ui` via `make codegen` |
| Primitive render styling | `@ze/ui/react` |
| WebSocket / onboarding wiring for UI actions | `apps/ze-web` |
| Page-level REST usage | `apps/ze-web` via `@ze/client` |

## Dependency graph

```
plugins / ze-api  →  ze-sdk  →  core packages
ze-web            →  @ze/client, @ze/ui
```
