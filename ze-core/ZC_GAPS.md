# Ze Core — Alignment Gaps

Temporary working document. Delete once all items are resolved.

---

## 1. ~~Database Schema~~ ✓ DONE

Alembic migration at `ze_core/migrations/versions/001_initial_schema.py`.
Programmatic runner at `ze_core/migrate.py`.

```bash
# manual
python -m ze_core.migrate upgrade head

# automatic at startup
ZC_AUTO_MIGRATE=true python ...
```

Install: `pip install 'ze-core[migrations]'` (adds alembic + psycopg2-binary).

---

## 2. `decompose` Node is a Stub (Blocker)

`ze_core/orchestration/nodes/routing.py` line 67:

```python
async def decompose(state: AgentState, config: dict) -> dict:
    return {}
```

Compound routing goes to this node but it does nothing — subtasks are never
populated, so compound agents always receive an empty task list.

`fallback.decompose()` already exists and produces the right `RoutingEnvelope`.
The node just needs to call it.

**Action:** Implement `decompose` to call `fallback.decompose()` using
`config["configurable"]["router"]._client` and the agent registry, then store
the result in `state["envelope"]`.

---

## 3. ~~Tool Execution Path~~ ✓ DONE

`BaseAgent` now provides two methods agents can call from `run()`:

- **`call_tool(name, ctx, **kwargs)`** — capability-gated dispatch. Suppresses
  WRITE tools in DRAFT mode; raises `ToolBlockedError` in BLOCKED mode.
- **`agentic_loop(ctx, client, messages, system, deps, ...)`** — full ReAct loop.
  LLM picks tools, ze_core dispatches them, loop repeats until the model returns
  text. Falls back to a plain `complete()` call when `max_iterations` is reached.

Module-level helpers (`_merge_deps`, `_serialise_result`, `_truncate_messages`)
live in `base_agent.py` and are importable for testing.

The design mirrors Ze Phase 16: no separate `ToolAgent` subclass — the loop
lives directly on `BaseAgent` and agents opt in by calling it from `run()`.

---

## 4. ~~Interface ↔ Graph Bridge~~ ✓ DONE

`Container.from_config()` now accepts an optional `interface` parameter.
`validate_interface()` is called immediately at startup — misconfigured
interfaces fail fast before any DB or embedder initialisation.

Two new methods on `Container`:

- **`invoke(prompt, session_id, ...)`** — runs the full conversation turn.
  Checks `pending_confirmation` after the first graph pass and handles both
  confirmation styles:
  - *inline*: calls `interface.confirm()`, resumes graph on approval,
    calls `interface.send()` with the final response.
  - *async*: calls `interface.send_confirmation()`, returns
    `InvokeResult(confirmation_pending=True)`.
  - *no interface*: returns `InvokeResult(confirmation_pending=True)` so
    callers can handle the pause themselves.

- **`resume(session_id)`** — for async style; called after the transport
  callback writes the decision into state. Resumes the graph with
  `ainvoke(None, config)` and delivers the final response.

`InvokeResult(session_id, response, confirmation_pending, error)` added to
`interface/types.py` and exported from `ze_core.interface`.

---

## 5. ~~`LLMClient` Protocol / `OpenRouterClient` Mismatch~~ ✓ DONE

`OpenRouterClient.complete()` now accepts `system`, `temperature`,
`response_format`, `**kwargs` and passes them through to the API payload.

`complete_with_tools(messages, model, tools, system, temperature, max_tokens)`
added to both `OpenRouterClient` and the `LLMClient` Protocol.

---

## 6. `ze_core/__init__.py` Has No Public API

Currently just a docstring. A consumer doing `from ze_core import Container`
gets an `ImportError`.

**Action:** Re-export the primary public surface:

```python
from ze_core.container import Container
from ze_core.orchestration import BaseAgent, agent
from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.memory import MemoryStore, MemoryConsolidator
from ze_core.settings import Settings
from ze_core.openrouter.client import OpenRouterClient
```

---

## 7. `asyncpg.Pool` as DI Key Forces Agent Hard-Dep on asyncpg

The container adds `asyncpg.Pool: pool` to the dependency map. An agent that
needs DB access must annotate `__init__(self, pool: asyncpg.Pool)`, which
requires importing asyncpg in the agent module.

Ze Core has `dependencies = []`, so this creates an implicit hard dependency
that breaks `_resolve()` if asyncpg is not installed.

**Action:** Either (a) document asyncpg as a required runtime dependency and
add it to `pyproject.toml` extras, or (b) introduce a `DBPool` type alias /
Protocol in `ze_core` that agents annotate against, keeping asyncpg an
implementation detail of the container.

---

## 8. `py.typed` Marker Missing

Without `ze_core/py.typed`, mypy and pyright treat the package as untyped and
ignore all annotations.

**Action:** `touch ze_core/py.typed` and add `"include": ["ze_core/py.typed"]`
to hatch build config.

---

## Summary Table

| # | Item | Severity | Effort |
|---|------|----------|--------|
| 1 | ~~Database schema (schema.sql / migration)~~ ✓ | Blocker | Small |
| 2 | `decompose` node is a stub | Blocker | Small |
| 3 | ~~Tool execution path~~ ✓ | High | Medium–Large |
| 4 | ~~Interface ↔ graph bridge~~ ✓ | High | Small–Medium |
| 5 | ~~`OpenRouterClient` / `LLMClient` mismatch~~ ✓ | Medium | Small |
| 6 | `ze_core/__init__.py` public API | Medium | Small |
| 7 | `asyncpg.Pool` DI key forces agent dep | Medium | Small |
| 8 | `py.typed` marker missing | Low | Trivial |
