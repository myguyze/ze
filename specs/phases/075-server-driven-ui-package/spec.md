# Server-Driven UI Package — Spec

> **Package:** `@ze/ui` (`packages/ze-ui/`)
> **Phase:** 75
> **Status:** Done
> **Depends on:** Phase 43 ([43-react-web-app.md](../043-react-web-app/spec.md)), Phase 66 ([66-primitive-ui.md](../066-primitive-ui/spec.md)), Phase 72 ([72-api-client-codegen.md](../072-api-client-codegen/spec.md)), Phase 73 ([73-api-surface.md](../073-api-surface/spec.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `packages/ze-ui/` workspace package | ✅ Done |
| Contract layer (`parse`, schema validation) | ✅ Done |
| React renderer (`@ze/ui/react`) | ✅ Done |
| `ze-web` migrated off local copies | ✅ Done |
| `make codegen` generates `@ze/ui` artifacts | ✅ Done |

---

## Purpose

Ze already has a server-driven UI contract in practice: the backend emits structured component payloads, and `ze-web` renders them inline. This phase turns that contract into a dedicated workspace package, analogous to `@ze/client`, so the UI schema, runtime validation, and React rendering API have one canonical import surface instead of being split across backend-local definitions and web-app-local copies. It supersedes the current in-tree `core/ze-components` frontend contract surface rather than layering a second path on top of it.

The package is intentionally split into a framework-neutral contract layer and a React renderer layer. The contract layer defines the primitive tree schema, parsing, and validation. The renderer layer provides the React implementation used by `ze-web` today and `ze-app` later if that app stays on React.

---

## Responsibilities

- Define the canonical TypeScript contract for server-driven UI primitive trees.
- Export runtime parsing and validation helpers derived from the same schema that defines the TypeScript types.
- Export a React renderer API for primitive trees through a dedicated subpath.
- Keep the contract layer framework-neutral so future consumers can reuse the same payload model without React-specific imports.
- Integrate the package into `scripts/codegen.ts` so generated contract artifacts stay in lockstep with the backend source of truth.
- Generate committed artifacts from the backend schema rather than hand-maintaining duplicated frontend types.
- Reject malformed or unknown payloads at parse time instead of silently accepting partial structures.

---

## Out of Scope

- Backward-compatible imports, reexports, aliases, or shim modules of any kind.
- Preserving the old package surface as a fallback path.
- Backend emission helpers, render tools, or builder functions.
- Non-React renderers.
- Runtime-only validation that is not derived from the canonical schema.
- Transport protocol changes to WebSocket frames beyond the existing `components` payload shape.
- New semantic UI primitives in this phase.

---

## Module Layout

```
packages/
└── ze-ui/
    ├── package.json
    ├── tsconfig.json
    └── src/
        ├── index.ts                 # framework-neutral contract surface
        ├── schema.ts                # exported schema metadata and types
        ├── parse.ts                 # parse / validate helpers
        ├── errors.ts                # parse and validation errors
        ├── react/
        │   ├── index.ts             # React renderer subpath export
        │   ├── PrimitiveRenderer.tsx
        │   └── primitives/
        │       ├── Col.tsx
        │       ├── Row.tsx
        │       ├── Text.tsx
        │       └── ...
        └── generated/
            ├── schema.json          # canonical JSON Schema for the primitive tree contract
            ├── types.gen.ts         # generated TypeScript types
            ├── validators.gen.ts    # generated runtime validators / parsers
            └── index.ts             # generated re-export surface for generated artifacts

scripts/
└── codegen.ts                       # emits @ze/client and @ze/ui generated artifacts
```

---

## Interface Contract

### Contract surface

The root package exposes the framework-neutral UI contract:

```ts
import type { Primitive, PrimitiveTree, PrimitiveNode } from "@ze/ui";
import { parsePrimitiveTree, validatePrimitiveTree } from "@ze/ui";
```

The contract layer must:

- Represent primitive trees as a discriminated union.
- Preserve the serialized payload shape used in websocket `components` frames.
- Expose a parser that returns a typed tree or throws a structured error.
- Expose a validator / type guard for callers that need a boolean check.

### React renderer surface

The React renderer is exported from a subpath:

```ts
import { PrimitiveRenderer } from "@ze/ui/react";
```

The renderer surface must:

- Render the validated primitive tree recursively.
- Keep the renderer logic colocated with the contract package rather than inside `ze-web`.
- Accept already-parsed contract objects, not raw unknown payloads.
- Avoid embedding business logic, message transport, or websocket state.

### Validation and parsing

Validation is schema-driven, not handwritten runtime-only guards.

The package must:

- Generate the runtime validator from the canonical schema emitted by the backend source of truth.
- Parse unknown input through that validator before any render logic runs.
- Reject unknown discriminators, missing required fields, and invalid nested child nodes.
- Surface a structured parse error that identifies the failing path and field.

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Unknown `type` discriminator | Fail validation and throw a parse error |
| Missing required field | Fail validation and throw a parse error |
| Invalid nested child node | Fail validation and throw a parse error with the nested path |
| Payload includes extra unsupported fields | Reject unless the schema explicitly allows them |
| Consumer passes raw `unknown` data directly to the renderer | Renderer should not be the parser; caller must parse first |
| Future payload version not understood by this package | Reject clearly rather than coercing |

---

## Data Structures

The TypeScript contract mirrors the backend primitive tree model. The exact field set is controlled by the canonical schema and generated into `src/generated/types.gen.ts`.

At minimum, the package exposes:

- `Primitive` discriminated union for all supported node types.
- `PrimitiveTree` for one or more root nodes.
- `PrimitiveNode` for recursive child values.
- `PrimitiveAction` for user-triggered button/action payloads.
- `PrimitiveValidationError` for parse failures.

The contract layer must remain framework-neutral even if the renderer surface is React-only.

---

## Code Generation

This phase extends `scripts/codegen.ts` so it produces both API client artifacts and UI contract artifacts in one pass.

The script must:

- Read the canonical UI schema from the backend source of truth directly.
- Generate TypeScript types for the primitive tree contract.
- Generate runtime validation / parsing artifacts from the same schema.
- Write all generated UI artifacts into `packages/ze-ui/src/generated/`.
- Keep the output committed and deterministic.
- Avoid requiring a running server for generation.

The generation step should be aligned with the existing API client codegen flow:

- OpenAPI extraction remains the source of truth for `@ze/client`.
- The server-driven UI schema extraction is the source of truth for `@ze/ui`.
- Both packages are regenerated by the same script so schema drift cannot hide in one surface while the other stays stale.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Backend UI schema source | Canonical definition of the primitive tree contract |
| `scripts/codegen.ts` | Single generation entrypoint for committed artifacts |
| `react` / `react-dom` | Renderer implementation for `@ze/ui/react` |
| JSON Schema validator (`ajv` or equivalent) | Runtime parser / validator derived from generated schema |
| `@ze/client` codegen pipeline | Existing pattern for generated workspace packages |

---

## Implementation Notes

- The backend remains responsible for emitting server-driven UI payloads into websocket frames; this phase only packages the frontend-facing contract and renderer API.
- The contract and renderer are intentionally separated by exports, not by implicit conventions.
- The root package should stay usable without importing React so validation and parsing can be shared by future consumers.
- The React renderer should be a thin view layer over already-validated primitive trees.
- `ze-web` must stop depending on local hand-written UI contract copies once this package exists.
- The old package surface is replaced, not bridged.

---

## Open Questions

- [x] Validation strategy? → **Schema-driven**. Runtime parsing and validation are generated from the canonical schema, not handwritten.
- [x] Package naming? → **`@ze/ui`**. The name stays broad enough for `ze-web` and a future React-based `ze-app`.
- [x] Renderer boundary? → **React-only renderer subpath**. The root package stays framework-neutral; `@ze/ui/react` carries the React implementation.
