# Package README template

Every package in the Ze monorepo must have a `README.md` at its root. Follow this
structure; omit sections that do not apply to the package type.

---

## Required structure

```markdown
# <package-name>

One-sentence description of the package's role in Ze.

## Role in Ze

Two short paragraphs: where this package sits in the architecture, and what
important capabilities it enables for users or plugin authors.

### Key features

- 3–6 bullets — the most important things this package brings

### Integration

How it wires into Ze: who consumes it, discovery/bootstrap path, graph or
container hooks. For plugins, list agents, jobs, channels, and stores contributed.

## Responsibilities

| Module | What it provides |
|---|---|
| `module/` | Brief description |

## Dependencies

## Usage | Running

## Configuration

## Testing

From the repo root:

```bash
make test-<short-name>
```

See [docs/testing.md](../docs/testing.md) for all targets and conventions.
```

---

## Section rules

| Section | Required | Notes |
|---|---|---|
| Title + one-liner | Yes | Match `description` in `pyproject.toml` where present |
| Role in Ze | Yes | Architecture context + `### Key features` + `### Integration` |
| Responsibilities | Yes | Module table — the primary map of what lives here |
| Dependencies | Yes | Mermaid diagram for plugins and apps; prose or list for core/integration |
| Usage / Running | Yes | Code examples or Makefile targets |
| Configuration | No | Only when the package reads env vars or YAML |
| Testing | Yes | Always document `make test-<short-name>`. See [docs/testing.md](./testing.md). |

---

## Package types

### `core/` — shared infrastructure

- **Role in Ze:** explain what layer of the stack this is and which packages depend on it.
- **Integration:** how `ze-core` or `ze-api` wires it; not imported by plugins directly (except via SDK re-exports).
- **Usage:** import examples for engine/SDK authors.

### `plugins/` — domain extensions

- **Role in Ze:** user-visible capabilities this domain adds to the assistant.
- **Integration:** entry point, `ZePlugin` hooks, agents/jobs/channels/stores contributed. Plugins that emit cross-domain events should implement `SignalSource` via `signal_sources()` (see `ze-news`, `ze-calendar`).
- **Import convention:** plugin code imports from `ze_sdk.*`, never `ze_plugin.*` or `ze_core.*`.

### `integrations/` — third-party wrappers

- **Role in Ze:** which external service and which plugins consume it.
- **Integration:** `ZeIntegration.from_settings`, bootstrap injection via `integration_types()`.
- **Setup:** OAuth flows, API keys.

### `apps/` — deployment units

- **Role in Ze:** how this package assembles the rest of the monorepo at runtime.
- **Running:** Makefile targets.
- Add protocol or API sections when they are the package's main purpose (e.g. WebSocket in `ze-api`).

---

## Parent directory READMEs

`core/README.md`, `plugins/README.md`, `integrations/README.md`, and `apps/README.md`
index their child packages. Keep the package table in sync when adding or removing packages.
