# Package README template

Every package in the Ze monorepo must have a `README.md` at its root. Follow this
structure; omit sections that do not apply to the package type.

---

## Required structure

```markdown
# <package-name>

One-sentence description of the package's role in Ze.

## Responsibilities

| Module | What it provides |
|---|---|
| `module/` | Brief description |

## Dependencies

## Usage | Extension point | Running

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
| Responsibilities | Yes | Module table — the primary map of what lives here |
| Dependencies | Yes | Mermaid diagram for plugins and apps; prose or list for core/integration |
| Usage / Extension point / Running | Yes | Pick one heading based on package type (see below) |
| Configuration | No | Only when the package reads env vars or YAML |
| Testing | Yes | Always document `make test-<short-name>` from repo root. See [docs/testing.md](../testing.md). |

---

## Package types

### `core/` — shared infrastructure

- **Extra section:** `## Usage` with import examples.
- **Rule:** no imports from `plugins/` or `apps/`.
- **Audience:** engine (`ze-core`, `ze-api`) and SDK re-exports — not plugin authors directly.

### `plugins/` — domain extensions

- **Extra section:** `## Extension point` — what the `ZePlugin` contributes (agents, jobs, channels, graph hooks).
- **Dependencies diagram:** show `ze-sdk` and peer plugins, not raw `ze-core`.
- **Import convention:** plugin code imports from `ze_sdk.*`, never `ze_plugin.*` or `ze_core.*`.

### `integrations/` — third-party wrappers

- **Extra section:** `## Usage` and optionally `## Setup` (OAuth flows, API keys).
- **Rule:** zero Ze package dependencies.

### `apps/` — deployment units

- **Extra section:** `## Running` with Makefile targets.
- Add protocol, API, or architecture sections only when they are the package's main purpose (e.g. WebSocket protocol in `ze-api`).

---

## Parent directory READMEs

`core/README.md`, `plugins/README.md`, `integrations/README.md`, and `apps/README.md`
index their child packages. Keep the package table in sync when adding or removing packages.
