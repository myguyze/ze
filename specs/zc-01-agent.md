# Ze Core — Agent Decorator & BaseAgent — Spec

## Purpose

Define the `@agent` decorator, the `BaseAgent` abstract class, and the
convention-based agent discovery mechanism. This is the central primitive of Ze
Core: the mechanism by which agents become self-describing and the framework
discovers them without explicit registration.

## Responsibilities

- `@agent` registers an agent class in the global registry at import time.
- `BaseAgent` defines the contract every agent must implement: `run()`, `stream()`,
  and a set of typed class attributes the framework reads at startup.
- Ze Core discovers agents by scanning the `agents/` directory at container startup,
  importing each `agent.py` it finds. `@agent` fires as a side effect of import.
- `enabled = False` on a class excludes the agent from routing and prevents
  instantiation. The class is still registered (import still works) but the
  framework skips it entirely during startup.
- `name` must be unique across all registered agents. Duplicate names raise at
  import time.

## Out of Scope

- Does not execute agent logic.
- Does not evaluate capability modes (that is the gate's job).
- Does not inject memory or persona context (that is the orchestration graph's job).
- Does not validate tool availability (that is the container's job at startup).

---

## The `@agent` Decorator

`ze_core/orchestration/registry.py`

```python
def agent(cls: type) -> type:
    """Register an agent class. Raises AgentConfigError on duplicate name."""
    name = getattr(cls, "name", None)
    if not name:
        raise AgentConfigError(f"{cls.__name__} must define a `name` class attribute")
    if name in _registry:
        raise AgentConfigError(f"Duplicate agent name {name!r}")
    _registry[name] = cls
    return cls
```

The decorator is a pure function — it mutates the registry and returns the class
unchanged. No metaclass magic, no wrapping.

### Registry accessors

```python
def get_agent_class(name: str) -> type[BaseAgent]:
    """Return the registered class for `name`. Raises UnknownAgentError if missing."""

def get_registered_agents() -> dict[str, type[BaseAgent]]:
    """Return all registered classes, including disabled ones."""

def get_enabled_agents() -> dict[str, type[BaseAgent]]:
    """Return only agents with enabled = True."""
```

---

## BaseAgent

`ze_core/orchestration/base_agent.py`

### Class Attributes

Every `BaseAgent` subclass declares its configuration as class attributes.
The framework reads these at startup; no config file is involved.

| Attribute | Type | Default | Required | Purpose |
|---|---|---|---|---|
| `name` | `str` | — | Yes | Unique identifier. Used as registry key and in routing logs. |
| `description` | `str` | — | Yes | Embedded at startup for cosine-similarity routing. Must be non-empty. |
| `model` | `str` | `"anthropic/claude-sonnet-4-5"` | No | Primary LLM model for this agent. |
| `model_simple` | `str \| None` | `None` | No | Cheaper model for simple requests. `None` means always use `model`. |
| `vision_capable` | `bool` | `False` | No | If `True`, agent receives raw image bytes alongside the prompt. |
| `timeout` | `int` | `30` | No | Seconds before the agent run is cancelled with `AgentTimeoutError`. |
| `enabled` | `bool` | `True` | No | If `False`, excluded from routing and not instantiated. |
| `capabilities` | `dict[str, Mode]` | `{}` | No | Maps intent names to `Mode`. Unknown intents default to `CONFIRM`. |
| `intent_map` | `dict[str, str]` | `{}` | No | Maps intent names to human-readable descriptions. First key is the primary intent. |
| `tools` | `list[str]` | `[]` | No | Names of tools this agent may call. Validated against the tool registry at startup. |

`name` and `description` with empty values raise `AgentConfigError` during
container startup validation, not at import time.

### Abstract Methods

```python
class BaseAgent(ABC):
    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent and return a complete result."""

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """Stream response tokens. Default raises NotImplementedError."""
        raise NotImplementedError
        yield  # make type checkers happy

    async def startup(self) -> None:
        """Called once after DI wiring. Override for warmup (e.g. warm HTTP connection)."""

    async def shutdown(self) -> None:
        """Called during app shutdown. Override for cleanup."""
```

### Example Agent

```python
from ze_core.orchestration import BaseAgent, agent
from ze_core.capability import Mode

@agent
class CalendarAgent(BaseAgent):
    name = "calendar"
    model = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    description = """
        Manages Google Calendar events. Use for creating, reading, updating,
        or deleting events, checking availability, or finding free time.
    """
    capabilities = {
        "read":   Mode.AUTONOMOUS,
        "create": Mode.CONFIRM,
        "update": Mode.CONFIRM,
        "delete": Mode.CONFIRM,
    }
    intent_map = {
        "read":   "Search and retrieve calendar events.",
        "create": "Create a new calendar event.",
        "update": "Modify an existing calendar event.",
        "delete": "Remove a calendar event.",
    }
    tools = ["list_events", "create_event", "update_event", "delete_event"]
    system_prompt = "..."

    def __init__(self, client: OpenRouterClient, credentials: GoogleCredentials):
        self._client = client
        self._credentials = credentials

    async def run(self, ctx: AgentContext) -> AgentResult:
        ...
```

---

## Convention-Based Discovery

`ze_core/container.py`

Ze Core discovers agents by scanning the `agents/` directory relative to the
application root. The application root is the directory containing `config.yaml`,
inferred from the path passed to `Container.from_config()`.

```
myapp/
  config.yaml          ← app root
  agents/
    research/
      agent.py         ← imported → @agent fires → ResearchAgent registered
      tools.py
    writer/
      agent.py         ← imported → @agent fires → WriterAgent registered
```

### Discovery Algorithm

```
1. Determine app_root = parent directory of config.yaml
2. agents_dir = app_root / "agents"
3. For each subdirectory in agents_dir (sorted, deterministic order):
   a. If subdirectory contains agent.py:
      b. Import as <package>.agents.<name>.agent
      c. @agent fires as side effect — class is registered
4. Validate all registered agents (see Startup Validation below)
5. Instantiate all enabled agents via DI resolution
```

The import path assumes the application package name matches the directory name.
Ze's agents import as `ze.agents.calendar.agent`, `ze.agents.research.agent`, etc.

### Startup Validation

After discovery and before instantiation, the container validates every registered
agent:

| Check | Failure |
|---|---|
| `name` is non-empty | `AgentConfigError` |
| `description` is non-empty | `AgentConfigError` |
| Each name in `tools` exists in the tool registry | `AgentConfigError` |
| Each key in `intent_map` exists in `capabilities` | `AgentConfigError` |
| At least one agent has `enabled = True` | `RoutingError` |

Validation failures abort startup. A misconfigured agent must not reach a running
server.

---

## The `Mode` Enum

Declared in `ze_core/capability/types.py`. Used in `capabilities` dicts on agent
classes.

```python
class Mode(str, Enum):
    AUTONOMOUS = "autonomous"   # execute immediately
    CONFIRM    = "confirm"      # pause and ask the user
    DRAFT_ONLY = "draft_only"   # generate but never execute
    DISABLED   = "disabled"     # block entirely
```

`Mode` inherits from `str` so `Mode.AUTONOMOUS == "autonomous"` is `True`. This
allows `capabilities` dicts to be compared against string values from session
overrides without explicit conversion.

---

## Shared Types

`ze_core/orchestration/types.py`

```python
@dataclass
class AgentContext:
    session_id: str
    prompt: str
    intent: str
    gate_decision: GateDecision = GateDecision.EXECUTE
    memory: MemoryContext = field(default_factory=MemoryContext)
    messages: list[dict] = field(default_factory=list)
    persona: dict = field(default_factory=dict)
    model: str | None = None       # None → agent uses its class-level model default
    reporter: ProgressReporter | None = None

@dataclass
class AgentResult:
    agent: str
    response: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_used: int = 0
    memory_proposals: list = field(default_factory=list)
    contact_proposals: list = field(default_factory=list)
```

---

## File Structure Convention

Each agent lives in its own subdirectory under `agents/`:

```
agents/
  calendar/
    __init__.py
    agent.py     # @agent class, system prompt, run(), stream()
    tools.py     # @tool definitions used by this agent
```

`agent.py` is the only file Ze Core scans for. `tools.py` must be imported by
`agent.py` (or the container's shared tools import) to register `@tool` definitions
before startup validation runs.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.capability.types` | `Mode` enum, `GateDecision` |
| `ze_core.orchestration.types` | `AgentContext`, `AgentResult`, `ToolCall` |
| `ze_core.errors` | `AgentConfigError`, `UnknownAgentError`, `AgentTimeoutError` |

---

## Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| `name` attribute missing from class | `AgentConfigError` at import time |
| Duplicate `name` across two classes | `AgentConfigError` at import time of the second |
| `description` is empty string | `AgentConfigError` at startup validation |
| `agents/` directory does not exist | `AgentConfigError` during discovery |
| No enabled agents after discovery | `RoutingError` during startup |
| Tool name in `tools` not in tool registry | `AgentConfigError` at startup validation |
| `intent_map` key not in `capabilities` | `AgentConfigError` at startup validation |
