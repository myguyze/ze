# Monorepo Layout — Four-Tier Directory Structure

## Status

Implemented (Phase 47, June 2026; extended with `integrations/` tier, June 2026)

## Context

The flat `packages/` directory grew to 15 packages with no structural signal about
their role in the system. A newcomer (or an AI coding agent) looking at the directory
had no way to distinguish shared infrastructure from domain plugins from deployment
units without reading every `pyproject.toml`.

Two forces drove the reorganisation:

1. **Navigability** — the directory should communicate architecture at a glance.
2. **Growth trajectory** — new domain plugins (`ze-finance`, `ze-legal`, …) are
   being added regularly; the structure should guide where they land without
   requiring a decision each time.

## Decision

Dissolve `packages/` and promote four self-describing directories to the repo root:

```
core/           # shared infrastructure — no domain knowledge
integrations/   # external service wrappers — no Ze domain knowledge
plugins/        # ZePlugin domain extensions
apps/           # deployment units
```

**`core/`** contains packages that could, in principle, be shipped as a standalone
"AI assistant framework": `ze-core`, `ze-memory`, `ze-browser`,
`ze-notifications`, `ze-components`. They have no knowledge of Ze's personal
assistant use-case.

**`integrations/`** contains thin wrappers around external services and APIs —
`ze-google` (Google OAuth2 / Calendar / Gmail), and future broker or data-provider
clients. These packages have no Ze domain knowledge and no dependency on `core/`
framework primitives. `plugins/` consume them; `core/` does not.

**`plugins/`** contains `ZePlugin` implementations — self-contained domain
subsystems that contribute agents, stores, jobs, and migrations through the plugin
seam: `ze-personal`, `ze-email`, `ze-calendar`, `ze-prospecting`, `ze-news`,
`ze-finance`, `ze-legal`. Dropping a new plugin directory here is the only change
required to add a new domain subsystem.

**`apps/`** contains runnable units: `ze-api` (the FastAPI/WebSocket backend that
wires all plugins) and `ze-app` (the Flutter client). These are the only places that
import from both `core/`, `integrations/`, and `plugins/`.

## Alternatives considered

**Keep `packages/` with subdirectories** (`packages/core/`, `packages/plugins/`,
`packages/apps/`). Rejected: adds one level of indirection with no benefit — the
three subdirectory names are self-describing without the `packages/` wrapper.

**Move all packages to repo root** (`ze/ze-core/`, `ze/ze-personal/`, …). Rejected:
mixes installable packages with repo metadata (`specs/`, `docs/`, `Makefile`) at the
same depth. The uv workspace glob cannot be `*` at the root without picking up
non-package directories.

## Consequences

- **No Python import changes.** Package names (`ze_core`, `ze_personal`, …) are
  unchanged. All cross-package deps use `{ workspace = true }` — no path references
  inside `pyproject.toml` files needed updating.
- **uv workspace glob** updated to `members = ["core/*", "plugins/*", "apps/*", "integrations/*"]`.
- **Makefile** path variables updated (`ZE`, `ZE_CORE`, and inline paths).
- New domain plugins go into `plugins/` — no structural decision required.
- New shared libraries (no domain knowledge) go into `core/`.
- New external service wrappers go into `integrations/` — no Ze framework deps allowed.
- The dependency rule is reinforced by directory placement: `core/` packages must
  never import from `plugins/`, `integrations/`, or `apps/`. `integrations/` packages
  must never import from `core/`, `plugins/`, or `apps/`.
