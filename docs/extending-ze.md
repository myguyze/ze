# Extending Ze

Ze is extended through **plugins** — self-contained domain packages that contribute
agents, proactive jobs, channels, and graph behaviour without touching the engine.
This guide covers the full lifecycle of building an extension: from deciding where code
belongs to wiring it into the running app.

Read this alongside:
- [docs/sdk.md](sdk.md) — SDK symbol reference
- [docs/adding-an-agent.md](adding-an-agent.md) — agent authoring details
- [docs/package-architecture.md](package-architecture.md) — package layout and dependency rules

---

## Where does my code belong?

Start here before writing anything.

```
New agent that needs existing domain state (goals, contacts, workflows)?
  → ze-personal  (ze_personal/agents/<name>/)

New agent for email/Gmail?
  → ze-email  (ze_email/agents/<name>/)

New agent for calendar/reminders?
  → ze-calendar  (ze_calendar/agents/<name>/)

New agent for prospecting/outreach?
  → ze-prospecting  (ze_prospecting/agents/)

New agent for a new coherent domain (finance, legal, health)?
  → new plugin package  (see "Creating a new plugin package" below)

New proactive background job?
  → same package as the agent it serves  (+  plugin.register_proactive_jobs())

New memory retrieval policy or graph predicate?
  → ze-memory

New export/import/delete data domain?
  → ze-data (re-exported from ze_sdk)

New stable authoring type or protocol?
  → ze-agents  (re-exported from ze_sdk)

New onboarding step/seed type or setup-flow primitive?
  → ze-onboarding  (re-exported from ze_sdk.onboarding)

New push notification backend?
  → ze-notifications

New server-driven UI component?
  → ze-components
```

See [docs/package-architecture.md](package-architecture.md) for the full decision table and the criteria for when a new package is actually warranted.

---

## Adding an agent to an existing plugin

The short path — no new package needed.

### 1. Write a spec first

Every implementation starts with a spec in `specs/phases/`. Use `specs/TEMPLATE.md`.
Resolve all open questions before writing code.

### 2. Create the agent files

```
plugins/<pkg>/<module>/agents/<name>/
    __init__.py
    agent.py      ← @agent class + _AGENT_INSTRUCTIONS
    tools.py      ← @tool functions (omit if no Python tools needed)
```

### 3. Define tools (`tools.py`)

```python
from ze_sdk import tool, ToolAccess

@tool(access=ToolAccess.READ, description="Fetch records from the store.")
async def get_record(id: str, store: MyStore) -> str:
    result = await store.get(id)
    return str(result)

@tool(access=ToolAccess.WRITE, description="Create a new record.")
async def create_record(name: str, store: MyStore) -> str:
    record = await store.create(name)
    return f"Created: {record.id}"
```

Use `ToolAccess.READ` when there are no external side effects. Use `ToolAccess.WRITE`
for anything that creates, modifies, deletes, or sends. When in doubt, use `WRITE`.

### 4. Write the agent (`agent.py`)

```python
from ze_sdk import agent, BaseAgent
from ze_sdk.types import AgentContext, AgentResult, Mode

_AGENT_INSTRUCTIONS = """
You are Ze's <name> agent. <Purpose, scope, tone.>

Guidelines:
- <specific constraint>
""".strip()


@agent
class MyAgent(BaseAgent):
    name         = "my_agent"
    description  = "One or two sentences. Embedded for routing — be specific."
    model        = "anthropic/claude-sonnet-4-5"
    timeout      = 30
    tools        = ["get_record", "create_record"]
    intents      = {
        "read":   Intent(Mode.AUTONOMOUS, "Retrieve a record."),
        "create": Intent(Mode.CONFIRM,    "Create a new record."),
    }

    def __init__(self, store: MyStore) -> None:
        self._store = store

    async def run(self, ctx: AgentContext) -> AgentResult:
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        messages = [{"role": "user", "content": ctx.prompt}]

        response, tool_calls = await self.agentic_loop(
            ctx, self._client, messages, system,
            deps={"store": self._store},
        )

        return AgentResult(agent=self.name, response=response, tool_calls=tool_calls)
```

**All `__init__` parameters must be type-annotated.** The bootstrapper uses
`get_type_hints()` — unannotated parameters raise `AgentConfigError` at startup.

### 5. Register with the plugin

```python
# In plugins/<pkg>/<module>/plugin.py
def agent_module_paths(self) -> list[str]:
    return [
        "mypkg.agents.myagent.tools",   # tools first — @tool registers on import
        "mypkg.agents.myagent.agent",
    ]
```

### 6. Add shared deps only when needed

Plugin discovery is automatic via the `ze.plugins` entry point. If your agent's
`__init__` takes a type that is not already in the bootstrap dep map, either:

- contribute it from an existing plugin via `agent_deps()`, or
- add the service to `plugin_deps` in `ze_api/container.py` inside `build_container()`
  when it is a shared infra type constructed before plugins load.

### 7. Register memory and checkpoint hooks

```python
def memory_policies(self) -> dict:
    from ze_memory.policies import MyAgentPolicy
    return {"my_agent": MyAgentPolicy()}

def checkpoint_serde_modules(self) -> tuple[str, ...]:
    return ("ze_myplugin.types",)
```

### 8. Write tests

```
plugins/<pkg>/tests/agents/<name>/
    __init__.py
    test_agent.py
    test_tools.py
```

- No real API calls — mock `client.complete_with_tools` with `AsyncMock`.
- No real DB — mock `pool.acquire()` with `AsyncMock`.
- Build `AgentContext` directly (it's a dataclass).
- Test draft mode: set `gate_decision=GateDecision.DRAFT`, assert WRITE tools return `is_draft=True`.
- Test blocked mode: set `gate_decision=GateDecision.BLOCKED`, assert `ToolBlockedError` is raised.

---

## Creating a new plugin package

Use this path when you have a coherent new domain (e.g. finance, health) that warrants
its own package. Read [docs/package-architecture.md](package-architecture.md#when-to-create-a-new-package)
first to confirm a new package is justified.

### 1. Scaffold the package

```
plugins/ze-myplugin/
    pyproject.toml
    ze_myplugin/
        __init__.py
        plugin.py
        types.py          ← domain dataclasses (never Pydantic)
        locales/
            en.yaml       ← progress message keys for this plugin
            pt.yaml
        agents/
            myagent/
                __init__.py
                agent.py
                tools.py
        jobs/
            myjob.py
        store.py
    tests/
        __init__.py
        agents/
            myagent/
                test_agent.py
```

### 2. `pyproject.toml`

```toml
[project]
name = "ze-myplugin"
version = "0.1.0"
dependencies = ["ze-sdk"]     # only Ze dep a plugin needs

[project.entry-points."ze.plugins"]
ze_myplugin = "ze_myplugin.plugin:MyPlugin"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

The `ze.plugins` entry point is the contract that declares the plugin's existence to Ze.

### 3. Implement the plugin

```python
# ze_myplugin/plugin.py
from pathlib import Path
from ze_sdk import ZePlugin

class MyPlugin(ZePlugin):

    def __init__(self, store: MyStore) -> None:
        self._store = store

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_myplugin.agents.myagent.tools",
            "ze_myplugin.agents.myagent.agent",
        ]

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent.parent / "migrations" / "versions"

    def configurable_services(self) -> dict:
        return {"my_store": self._store}

    def memory_policies(self) -> dict:
        from ze_memory.policies import MyAgentPolicy
        return {"my_agent": MyAgentPolicy()}

    def checkpoint_serde_modules(self) -> tuple[str, ...]:
        return ("ze_myplugin.types",)

    async def startup(self, container) -> None:
        await self._store.connect()

    async def shutdown(self) -> None:
        await self._store.close()

    def register_proactive_jobs(self, scheduler, settings, *, consolidation_enabled=True) -> None:
        from ze_myplugin.jobs.myjob import MyJob
        scheduler.add_cron_job(MyJob(self._store, settings), cron="0 9 * * *")
```

Override only what you need — all methods have no-op defaults.

### 3b. Add progress message translations

Create `ze_myplugin/locales/en.yaml` (and `pt.yaml` for Portuguese):

```yaml
# ze_myplugin/locales/en.yaml
my_agent:
  working:
    - "⚙️ Working on that..."
    - "⚙️ Let me handle that..."
```

The `ZePlugin` base class auto-loads these files via `locale_data()` at startup and
merges them into the shared `ProgressTranslations`. No override needed — just follow
the `locales/{locale}.yaml` convention. Agents call `await self.emit(ctx, "my_agent.working")`
to send the message to the client.

The app-level `config/locales/` files are an override layer — add entries there only
to customise a plugin's messages for a specific deployment without touching plugin code.

### 4. Add to `ze-api` dependencies

```toml
# apps/ze-api/pyproject.toml
[project]
dependencies = [
    ...
    "ze-myplugin",
]
```

Ze discovers and instantiates the plugin at startup via the entry point. Only add
types to `plugin_deps` in `build_container()` when the plugin constructor needs a
shared service that is not already in the dep map.

### 5. Create a database migration

```bash
make migrate-create msg="add myplugin tables"
```

Write the SQL in `apps/ze-api/migrations/versions/<timestamp>_add_myplugin_tables.py`.
Follow the pattern of existing migrations — raw SQL, no ORM.

---

## Adding a proactive job

Background jobs run on a cron schedule and push notifications to the user.

### 1. Implement the job

```python
# ze_myplugin/jobs/myjob.py
from ze_sdk.proactive import proactive_job, ProactiveNotifier
from ze_agents.settings import Settings

@proactive_job
class MyJob:
    job_id   = "my_plugin.my_job"
    schedule = "0 9 * * 1"   # every Monday 09:00

    def __init__(self, store: MyStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    async def run(self, notifier: ProactiveNotifier) -> None:
        data = await self._store.fetch_summary()
        if not data:
            return
        await notifier.send(title="Weekly summary", body=data)
```

### 2. Register in the plugin

```python
def register_proactive_jobs(self, scheduler, settings, *, consolidation_enabled=True) -> None:
    from ze_myplugin.jobs.myjob import MyJob
    scheduler.add_cron_job(MyJob(self._store, settings), cron="0 9 * * 1")
```

---

## Adding a channel

Channels represent message transports (email, SMS, etc.).

```python
from ze_sdk.channels import Channel, ChannelType, Message, SentMessage, Thread

class MyChannel(Channel):
    channel_type = ChannelType.EMAIL   # or define a new ChannelType value

    async def send(self, handle: str, message: Message) -> SentMessage: ...
    async def receive(self, thread_id: str) -> list[Message]: ...
    async def list_threads(self) -> list[Thread]: ...
```

Register the channel in your plugin's `startup()` via the `ChannelRegistry`.

---

## Capability model

Every agent intent maps to a `Mode` that controls what the capability gate allows.

| Mode | Gate decision | Effect |
|------|--------------|--------|
| `AUTONOMOUS` | `EXECUTE` | All tools run immediately. |
| `CONFIRM` | `AWAIT_CONFIRMATION` | Graph pauses; user must approve before execution continues. |
| `DRAFT_ONLY` | `DRAFT` | WRITE tools return `is_draft=True` without executing. |
| `DISABLED` | `BLOCKED` | All tools raise `ToolBlockedError`. |

Agents declare capabilities per-intent via `intents`. Only declare intents the
agent meaningfully uses:

```python
intents = {
    "read":   Intent(Mode.AUTONOMOUS, "Retrieve records."),
    "write":  Intent(Mode.CONFIRM,    "Create or update a record."),
    "delete": Intent(Mode.DISABLED,   "Delete a record."),
}
```

For any intent not listed, the gate falls back to `default_mode` (default:
`Mode.CONFIRM`). Read-only agents that should never produce a confirmation
dialog regardless of intent should set `default_mode = Mode.AUTONOMOUS`.

Use `CONFIRM` for any action with real-world consequences (sending email, creating
calendar events, spending money). Use `AUTONOMOUS` only for read-only operations.

---

## Error handling

Raise typed errors from `ze_sdk.errors`. Never raise bare `Exception` or `ValueError`.

```python
from ze_sdk.errors import AgentError, ToolBlockedError

# In a tool:
if not result:
    raise AgentError("Record not found — cannot proceed.")

# ToolBlockedError is raised automatically by call_tool when gate is BLOCKED.
# You do not need to raise it yourself.
```

The error hierarchy:
- `ZeError` — base class
  - `AgentError` — unrecoverable agent failure
    - `AgentAbortedError` — loop cancelled via `AbortToken`
    - `AgentConfigError` — misconfiguration caught at startup
    - `ToolBlockedError` — tool rejected by the capability gate
  - `ChannelSendError` — channel transport failure

---

## Checklist

### New agent in an existing plugin

- [ ] Spec written in `specs/phases/`
- [ ] `agent.py` with `@agent` class — `name`, `description`, `model`, `intents`, `tools` set
- [ ] `tools.py` with `@tool` functions — `access` and `description` set on each
- [ ] Module paths added to `plugin.agent_module_paths()` (tools module listed first)
- [ ] All `__init__` parameters type-annotated
- [ ] New dependencies added to `container.py` dep_map
- [ ] Progress keys added to `locales/en.yaml` (and `pt.yaml`) in the plugin package
- [ ] Tests cover the golden path, draft mode, and blocked mode

### New plugin package

- [ ] Spec written in `specs/phases/` or `specs/arch/`
- [ ] `pyproject.toml` with `ze-sdk` as the only Ze dep and `ze.plugins` entry point
- [ ] `plugin.py` implementing `ZePlugin` — only overrides methods it needs
- [ ] `locales/en.yaml` (and `pt.yaml`) with progress keys for all agents in the plugin
- [ ] `ZePlugin.onboarding()` implemented if the plugin needs first-run setup questions
- [ ] Plugin instantiated in `ze_api/container.py` and added to `plugins` list
- [ ] Package added to `ze-api/pyproject.toml` dependencies
- [ ] At least one Alembic migration in `migrations/versions/`
- [ ] `tests/` directory with its own `pyproject.toml` or in-tree conftest
- [ ] `startup()` and `shutdown()` implemented if the plugin holds long-lived resources
