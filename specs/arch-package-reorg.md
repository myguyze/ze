# Ze — Package Architecture Reorganisation

## Context

Ze has grown from a single monorepo package into a multi-package monorepo. As domain
capabilities accumulate, `ze_core` has taken on two conflicting roles: pure
infrastructure (orchestration, routing, memory, telemetry) and domain services
(contacts, goals, workflow, persona). This spec defines how to separate those roles
and establish a repeatable pattern for future domain extensions.

The coupling runs deeper than imports: domain types (`ContactProposal`, `PersonContext`,
`WorkflowStep`) are embedded in `AgentState` and `AgentContext`, and domain nodes
(`load_workflow_step`, `verify_step`, `workflow_synthesize`) are baked into the
LangGraph graph in `ze_core`. A shallow module move would flip the dependency direction.
The fix requires the graph itself to be extensible.

---

## Goals

1. `ze_core` becomes **pure infrastructure** — no domain knowledge, no domain types.
2. A new **`ze-personal`** package holds the personal-assistant domain layer.
3. A **`ZePlugin` ABC** in `ze_core` defines a deep seam: plugins contribute agents,
   jobs, graph nodes, state extensions, and configurable services.
4. `ze` registers plugins **explicitly** in `ZeContainer` — no magic discovery.
5. The `AppInterface` implementation naming is **aligned** across packages.

---

## In scope

### 1. Deep `ZePlugin` ABC in `ze_core`

New file `ze_core/plugin.py`:

```python
class ZePlugin(ABC):
    # Container level
    def agents(self) -> list[type[BaseAgent]]: return []
    def jobs(self) -> list[ProactiveJob]: return []
    def migrations_path(self) -> Path | None: return None

    # Graph level
    def state_extensions(self) -> type[TypedDict] | None: return None
    def graph_nodes(self) -> dict[str, Callable]: return {}
    def graph_edges(self, builder: StateGraph) -> None: pass
    def configurable_services(self) -> dict[str, Any]: return {}
```

The graph builder in `ze_core` calls each registered plugin's graph-level methods after
building the base graph, allowing plugins to wire their own nodes and edges without
touching `ze_core`.

### 2. Strip the base graph to infrastructure only

`ze_core/orchestration/` retains only nodes that have zero domain knowledge:

| Node | Stays in `ze_core` | Reason |
|---|---|---|
| `transcribe` / `caption` | Yes | Multimodal preprocessing |
| `embed_route` | Yes | Pure routing |
| `decompose` | Yes | Compound query split |
| `fetch_context` | Yes | Memory retrieval |
| `capability_check` | Yes | Gate enforcement |
| `execute_tool` | Yes | Agent dispatch / ReAct loop |
| `draft_response` | Yes | Confirmation drafting |
| `await_confirmation` | Yes | Graph pause |
| `write_memory` | Yes (base) | Core memory write, no extractors |
| `synthesize` | Yes | Final response synthesis |
| `load_workflow_step` | No → `ze_personal` | Workflow domain |
| `verify_step` | No → `ze_personal` | Workflow domain |
| `workflow_synthesize` | No → `ze_personal` | Workflow domain |
| `workflow_failed` | No → `ze_personal` | Workflow domain |

The contact extraction that currently runs inside `write_memory` becomes a **memory
hook** — a callable registered by `ze_personal` and invoked post-write. The persona
identity block (`build_identity_block`) used in `base_agent.py` becomes an injectable
callable supplied via `configurable_services()`.

### 3. Extensible `AgentState`

`AgentState` in `ze_core` retains only core fields (routing, memory, agent result,
confirmation, error). Domain-specific fields move out:

| Field | Moves to |
|---|---|
| `workflow_steps` | `ze_personal` state extension |
| `workflow_step_results` | `ze_personal` state extension |
| `current_step_index` | `ze_personal` state extension |
| `workflow_execution_id` | `ze_personal` state extension |
| `contact_proposals` | `ze_personal` state extension |

`AgentContext` and `AgentResult` gain an `extensions: dict[str, Any]` field for
plugin-specific data. `ze_personal` reads and writes keyed namespaces (`"contacts"`,
`"contact_proposals"`) within `extensions`. Type-safe accessors live in `ze_personal`.

### 4. Create `ze-personal` package

New package at `packages/ze-personal/` with namespace `ze_personal`.

Modules moved from `ze_core` → `ze_personal`:

| Module | Contents |
|---|---|
| `contacts/` | `PersonStore`, `ContactChannelStore`, consolidator, extractors, tools, types |
| `goals/` | `GoalStore`, `GoalPlanner`, `GoalExecutor`, types |
| `workflow/` | `WorkflowStore`, planner, scheduler, types |
| `persona/` | `PostgresPersonaStore`, identity builder, types |

`ze_personal` also contains:
- `graph/workflow.py` — the four workflow graph nodes (moved from `ze_core`)
- `graph/memory_hooks.py` — contact extraction hook for post-memory-write
- `plugin.py` — `PersonalPlugin(ZePlugin)` implementation

Migrations that cover these domains move to `ze_personal/migrations/`:
- `003_goals_and_persona.py`
- `005_contacts_and_channels.py`

`ze-personal` depends on `ze-core`. It does **not** depend on `ze`.

### 5. `PersonalPlugin` wiring

`PersonalPlugin` implements all plugin methods:

```python
class PersonalPlugin(ZePlugin):
    def agents(self): return [GoalAgent]
    def jobs(self): return [ContactReviewJob, ...]
    def migrations_path(self): return Path(__file__).parent / "migrations"
    def state_extensions(self): return PersonalAgentState   # TypedDict subclass
    def graph_nodes(self): return {
        "load_workflow_step": load_workflow_step,
        "verify_step": verify_step,
        ...
    }
    def graph_edges(self, builder): ...  # wires workflow subgraph
    def configurable_services(self): return {
        "identity_builder": build_identity_block,
        "contact_extractor": extract_contacts,
    }
```

Registered in `ze/container.py`:

```python
container.register_plugin(PersonalPlugin(...))
```

### 6. Interface naming alignment

`ze/telegram/app_interface.py` → `ze/telegram/interface.py`

Class name `TelegramAppInterface` is unchanged. Aligns with:
`ze_core/interface/base.py` (ABC) → `ze/telegram/interface.py` (implementation).

### 7. Import and dependency updates

- All `ze` imports of `ze_core.contacts`, `ze_core.goals`, `ze_core.workflow`,
  `ze_core.persona` updated to `ze_personal.*`
- `ze-personal` added to `ze/pyproject.toml` dependencies
- `ze-core/pyproject.toml` loses all domain-related deps
- Tests in `ze-core/tests/` for moved modules move to `ze-personal/tests/`
- CLAUDE.md updated to reflect new layout

---

## Out of scope

- **`ze/google/` reorganisation** — deferred, no change
- **`ze-finance` implementation** — this spec establishes the pattern; `ze-finance`
  is a future phase
- **Moving agents out of `ze/agents/`** — agents stay in the app package for now
- **Entry-point / auto-discovery plugin loading** — explicit registration only
- **New features** — zero new behaviour; this is a structural refactor
- **API or Telegram behaviour changes** — nothing visible to the user changes

---

## Implementation order

1. Add `ZePlugin` ABC and extend graph builder to call plugin hooks — `ze_core` only,
   no behaviour change yet (plugins list is empty).
2. Make `AgentState` extensible; add `extensions` to `AgentContext`/`AgentResult`.
3. Extract workflow nodes out of `ze_core` graph into a standalone module; make
   `build_identity_block` injectable; wire contact extraction as a memory hook.
   Verify `ze_core` base graph works with no plugins registered.
4. Scaffold `ze-personal` package; move domain modules; move tests; update imports.
5. Implement `PersonalPlugin`; register in `ze/container.py`; run full test suite.
6. Rename `ze/telegram/app_interface.py` → `ze/telegram/interface.py`; update imports.
7. Update CLAUDE.md, `specs/00-overview.md`.

---

## Success criteria

| Criterion | How to verify |
|---|---|
| `make test` passes | CI green |
| `make test-all` passes | CI green |
| `ze_core` contains zero imports from `contacts`, `goals`, `workflow`, `persona` namespaces | `grep -r "ze_core\.contacts\|ze_core\.goals\|ze_core\.workflow\|ze_core\.persona" packages/ze-core` returns nothing |
| `ze` contains zero imports from old `ze_core` domain paths | `grep -r "from ze_core\.contacts\|from ze_core\.goals\|from ze_core\.workflow\|from ze_core\.persona" packages/ze` returns nothing |
| `ze_core` base graph runs end-to-end with an empty plugin list | Unit test with no plugins registered |
| Adding a second domain plugin requires no changes to `ze_core` | Verified by design; `ze-finance` stub check |
| `TelegramAppInterface` importable from `ze.telegram.interface` | `python -c "from ze.telegram.interface import TelegramAppInterface"` |
| `CLAUDE.md` repository layout reflects new structure | Review |
