# Ze — Plugin Agent Migration

## Context

Following `specs/arch-package-reorg.md` (Phase 20), `ze-personal` holds the domain layer
(contacts, goals, workflow, persona) but the domain agents (`GoalAgent`, `WorkflowManagerAgent`)
still live in `ze/agents/`. This spec completes the separation by migrating those agents into
`ze-personal` and teaching `bootstrap_agents()` to discover and instantiate plugin agents.

---

## Goals

1. `GoalAgent` and `WorkflowManagerAgent` live in `ze_personal/agents/` — they only import
   from `ze_core` and `ze_personal`, with no `ze/` dependencies.
2. `ZePlugin` gains `agent_module_paths()` so domain packages declare which agent modules
   to import at startup (triggering `@agent` registration).
3. `bootstrap_agents()` accepts `plugins` and imports plugin agent modules before the
   existing `ze/agents/` scan; the same `_resolve()` DI mechanism instantiates all agents.
4. `PersonalPlugin.agent_module_paths()` returns the paths for both domain agents.
5. Zero behaviour change — routing, capabilities, and tool execution are unaffected.

---

## In scope

### 1. `ZePlugin.agent_module_paths()` method

New optional hook in `ze_core/plugin.py`:

```python
def agent_module_paths(self) -> list[str]:
    """Fully-qualified module paths to import at bootstrap to trigger @agent registration.

    Modules are imported before ze/ agent discovery, so plugin agents are in the
    @agent registry when bootstrap resolves instances.
    """
    return []
```

### 2. Move `GoalAgent` → `ze_personal/agents/goals/`

Files:
- `ze_personal/agents/__init__.py`
- `ze_personal/agents/goals/__init__.py`
- `ze_personal/agents/goals/agent.py`  (from `ze/agents/goals/agent.py`)
- `ze_personal/agents/goals/tools.py`  (from `ze/agents/goals/tools.py`)

Changes during move:
- Remove `settings: Settings` parameter and `self._settings` — unused, eliminates the `ze/`
  import dependency.
- Update all `ze_core.*` / `ze_personal.*` imports to use new paths.
- `agent.py` imports its own `tools` module to trigger `@tool` registration:
  ```python
  import ze_personal.agents.goals.tools  # noqa: F401
  ```

### 3. Move `WorkflowManagerAgent` → `ze_personal/agents/workflow/`

Files:
- `ze_personal/agents/workflow/__init__.py`
- `ze_personal/agents/workflow/agent.py`  (from `ze/agents/workflow/agent.py`)
- `ze_personal/agents/workflow/tools.py`  (from `ze/agents/workflow/tools.py`)

Same changes:
- Remove `settings: Settings` — unused.
- Update imports; agent.py self-imports tools module.

### 4. `PersonalPlugin.agent_module_paths()`

```python
def agent_module_paths(self) -> list[str]:
    return [
        "ze_personal.agents.goals.agent",
        "ze_personal.agents.workflow.agent",
    ]
```

### 5. Update `bootstrap_agents()` signature

Add `plugins: list | None = None` parameter. Import plugin module paths before the
existing `ze/agents/` scan:

```python
def bootstrap_agents(..., plugins=None):
    # 1. Import plugin agent modules (triggers @agent + @tool registration)
    for plugin in (plugins or []):
        for module_path in plugin.agent_module_paths():
            importlib.import_module(module_path)

    # 2. Existing ze/ scan (now excludes goals + workflow)
    _import_agent_modules()

    # 3. Same _resolve() loop — works for all @agent classes
    for name, cls in get_registered_agents().items():
        ...
```

### 6. `build_container()` passes plugins to bootstrap

```python
bootstrap_agents(..., plugins=plugins)
```

### 7. Remove goal + workflow from `ze/agents/`

Delete:
- `ze/agents/goals/`
- `ze/agents/workflow/`

Update `ze/agents/bootstrap.py`:
- Remove `GoalStore`, `GoalPlanner`, `GoalExecutor`, `WorkflowStore`, `WorkflowPlanner`,
  `WorkflowScheduler` imports (no longer needed directly by bootstrap — they stay in
  `_dep_map` via type annotation resolution on the moved agent constructors).

---

## Out of scope

| Item | Reason |
|---|---|
| `CompanionAgent` | Imports `ze.agents.prospecting.tools` and `asyncpg.Pool` — `ze/` dependencies |
| `ResearchAgent` | Pure infrastructure, no domain deps, no reason to move |
| `CalendarAgent`, `EmailAgent` | Hard `ze.google` dependencies |
| `RemindersAgent` | Hard `ze.reminders` dependency |
| `ProspectingAgent` | Hard `ze_browser` + `ze.google` dependencies |
| Moving `ZePlugin.agents()` to return instances | Unnecessary — `_resolve()` handles DI from types |
| Auto-discovery of plugin agents | Explicit `agent_module_paths()` is clearer and safer |
| Moving agent tests | Tests in `ze/tests/agents/goals/` and `ze/tests/agents/workflow/` move to `ze-personal/tests/agents/` |

---

## Implementation order

1. Add `agent_module_paths()` to `ZePlugin` ABC in `ze_core/plugin.py`.
2. Update `bootstrap_agents()` to accept and apply `plugins`.
3. Update `build_container()` to pass `plugins` to `bootstrap_agents()`.
4. Move `ze/agents/goals/` → `ze_personal/agents/goals/` (drop `settings` dep, add tools import).
5. Move `ze/agents/workflow/` → `ze_personal/agents/workflow/` (drop `settings` dep, add tools import).
6. Implement `PersonalPlugin.agent_module_paths()`.
7. Update `ze/agents/bootstrap.py` — remove now-unused domain imports.
8. Move agent tests to `ze-personal/tests/agents/`.
9. Run full test suite (`make test`).
10. Commit.

---

## Success criteria

| Criterion | How to verify |
|---|---|
| `make test` passes | CI green |
| `ze/agents/goals/` and `ze/agents/workflow/` are deleted | `ls ze/agents/` |
| `GoalAgent` importable from `ze_personal.agents.goals.agent` | `python -c "from ze_personal.agents.goals.agent import GoalAgent"` |
| `ze_personal` has no `ze/` imports (except ze_core) | `grep -r "from ze\." ze_personal/` returns nothing |
| `bootstrap_agents()` accepts `plugins` without breaking non-plugin call sites | Existing tests pass |
