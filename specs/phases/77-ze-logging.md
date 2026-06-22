# ze-logging — Spec

> **Package:** `core/ze-logging`
> **Phase:** 77
> **Status:** Done
> **Prerequisite:** Phase 76 (ze-api shell cleanup — removes duplicate `ze_api/logging.py`)

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `core/ze-logging` package | ✅ Done |
| Move implementation from `ze_api/logging.py` | ✅ Done |
| `ze_agents.logging` → re-export shim | ✅ Removed — all imports use `ze_logging` |
| `ze_sdk` re-export update | ✅ Done |
| Delete `ze_api/logging.py` | ✅ Done |
| Wire `bind_context` in WebSocket turns | ✅ Done |
| Tests migrated | ✅ Done |

---

## Purpose

Logging is process infrastructure — structlog configuration, output routing (stdout,
optional file tee), and per-request context binding. It is not agent API, not
orchestration, and not deployment-shell logic.

Today the implementation is split incorrectly:

| Location | What it has | Problem |
|----------|-------------|---------|
| `ze_agents/logging.py` | `get_logger()` only | Wrong owner — agents package is the developer API, not infra |
| `ze_api/logging.py` | Full structlog setup + duplicate `get_logger` | Wrong layer — libraries should not import ze-api |

This phase extracts logging into `ze-logging`, a zero–Ze-dependency core package
(modelled on `ze-data` and `ze-notifications`). Entrypoints configure logging once;
every other package calls `get_logger`.

---

## Responsibilities

- `configure_logging(level, dev, log_file)` — call once at process startup
- `get_logger(name) -> structlog.BoundLogger` — call everywhere else
- `bind_context(session_id, agent=None)` / `unbind_context()` — async context vars for structured fields
- `_TeeStream` and file-append handling for dev `LOG_FILE` tee

---

## Out of Scope

- Log aggregation, shipping, or external sinks (Datadog, Loki, etc.)
- Per-agent log levels or routing rules
- Reading env vars or YAML — entrypoints pass explicit args to `configure_logging()`
- Stdlib `logging` bridge beyond what structlog already provides
- Replacing structlog with another backend

---

## Module Location

```
core/ze-logging/
├── pyproject.toml          # deps: structlog only
├── tests/
│   └── test_logging.py     # moved from apps/ze-api/tests/test_logging.py
└── ze_logging/
    └── __init__.py         # public API (flat — no submodules needed)
```

---

## Interface Contract

```python
# ze_logging/__init__.py

def configure_logging(
    level: str = "INFO",
    *,
    dev: bool = False,
    log_file: str = "",
) -> None:
    """Configure structlog for the current process. Idempotent; safe to call in tests."""

def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound logger. Must not configure output — assumes configure_logging ran."""

def bind_context(session_id: str, agent: str | None = None) -> None:
    """Bind session_id (and optional agent) to structlog contextvars for this async task."""

def unbind_context() -> None:
    """Clear structlog contextvars."""
```

### Invariants

| Rule | Rationale |
|------|-----------|
| Libraries never call `configure_logging` | Avoid import-order races and duplicate configuration |
| `get_logger` is cheap and side-effect free | Safe at module import time |
| JSON in production (`dev=False`), ConsoleRenderer in dev | Current behaviour preserved |
| File tee is append + line-buffered | Safe for `tail -f` during local dev |

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| `get_logger` before `configure_logging` | structlog default config — acceptable in unit tests; entrypoints must configure first |
| Invalid `level` string | Fall back to `logging.INFO` (current behaviour via `getattr`) |
| `log_file` parent dir missing | Create with `mkdir(parents=True, exist_ok=True)` |

---

## Configuration

Env vars stay on **`ZeApiSettings`** (ze-api shell). ze-api lifespan reads them and
calls `configure_logging`:

```python
configure_logging(
    settings.log_level,
    dev=settings.log_dev,
    log_file=settings.log_file,
)
```

Other entrypoints (eval CLI, scripts) pass their own values or rely on defaults.

| Env var | Owner | Used by |
|---------|-------|---------|
| `LOG_LEVEL` | `ZeApiSettings` | ze-api lifespan |
| `LOG_DEV` | `ZeApiSettings` | ze-api lifespan |
| `LOG_FILE` | `ZeApiSettings` | ze-api lifespan |

No new YAML block.

---

## Dependencies

```
ze-logging          structlog>=24.4
    ↑
ze-agents           depends on ze-logging; re-exports get_logger (shim)
ze-sdk              re-exports get_logger from ze_logging
ze-api              depends on ze-logging; calls configure_logging at startup
```

| Package | Depends on ze-logging? | Notes |
|---------|------------------------|-------|
| `ze-logging` | — | No Ze deps |
| `ze-agents` | yes | Drop direct `structlog` dep from pyproject; import from `ze_logging` |
| `ze-core`, plugins | via `ze_agents` or `ze_sdk` | No direct dep unless a package imports without ze-agents (prefer SDK) |
| `ze-api` | yes | Only shell module that calls `configure_logging` |
| `integrations/*` | no | Integrations don't log today; add only if needed |

---

## Migration

### 1. Create `core/ze-logging`

Move body of `apps/ze-api/ze_api/logging.py` → `ze_logging/__init__.py` unchanged
(behaviour-preserving).

Add to workspace root `pyproject.toml` and `ze-api/pyproject.toml` dependencies.

### 2. Shim in `ze_agents`

```python
# ze_agents/logging.py — becomes a one-line re-export
from ze_logging import bind_context, configure_logging, get_logger, unbind_context

__all__ = ["bind_context", "configure_logging", "get_logger", "unbind_context"]
```

Existing `from ze_agents.logging import get_logger` (~100 call sites) keeps working
without a mass import rewrite.

### 3. Update `ze_sdk`

```python
# ze_sdk/__init__.py
from ze_logging import get_logger  # was ze_agents.logging
```

Plugin authors importing `get_logger` from `ze_sdk` get the canonical path.

### 4. Delete `ze_api/logging.py`

Update ze-api imports:

```python
# Before
from ze_api.logging import configure_logging, get_logger

# After
from ze_logging import configure_logging, get_logger
```

Files affected (~10): `api/app.py`, `container.py`, `interface/native.py`,
`api/websocket/*.py`, `api/routes/eval.py`, `api/routes/data.py`.

### 5. Tests

- Move `apps/ze-api/tests/test_logging.py` → `core/ze-logging/tests/test_logging.py`
- Update imports to `from ze_logging import ...`
- ze-api test conftest: call `configure_logging()` via `ze_logging` if needed
- Add `make test-logging` target (or fold into existing `make test-agents`)

### 6. Docs

- `apps/ze-api/README.md` — remove `logging.py` from module table
- `CLAUDE.md` repository layout — add `ze-logging` under `core/`
- `docs/configuration.md` — note `LOG_*` vars configure via ze-api → `ze_logging`

---

## WebSocket context binding

`bound_turn_context(thread_id)` in `ze_api/api/websocket/context.py` wraps user turns
and confirmation resumes. `session_id` in structured logs equals the LangGraph
`thread_id`. Agent name is not bound at the WebSocket layer — routing sets agent
context inside the graph if needed later.

---

## Verification

```bash
make test-logging   # or core/ze-logging/tests
make test-api
make test-agents
make lint
grep -r "ze_api\.logging" apps/ core/ plugins/   # expect zero hits
```

---

## Open Questions

- [x] **New package vs expand ze-agents?** → New `ze-logging` package. Logging is infra, not agent API.
- [x] **Who owns env vars?** → ze-api shell (`ZeApiSettings`); `ze-logging` is env-agnostic.
- [x] **Mass import rewrite?** → Yes. All call sites import `ze_logging` directly; no shim in `ze_agents`.
- [ ] **Eval server configure_logging?** → Deferred. Eval doesn't configure structlog today; add when eval gets its own entrypoint.
