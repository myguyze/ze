# Agents — Spec

## Purpose

Define the five sub-agents of Ze. Each agent is an isolated module with its own
system prompt, tool registry, model config, and intent→tool map. Agents are
registered via a decorator and discovered dynamically — the orchestration layer
never imports individual agent modules directly.

## Responsibilities (all agents)

- Implement the `BaseAgent` interface.
- Register with `@register("<name>")` in `agents/registry.py`.
- Own a system prompt defined in `prompt.py` — no inline strings.
- Define a deterministic intent→tool map in `intent_map.py`.
- Implement tool functions in `tools.py`.
- Return an `AgentResult` from every `run()` call, including `memory_proposals`.
- Write an episode to memory after execution (via `MemoryStore`).
- Never call tools outside its own registry.
- Never call another agent directly.

## Registry Pattern

`ze/agents/registry.py` owns the agent registry.

```python
from ze.agents.base import BaseAgent

_REGISTRY: dict[str, type[BaseAgent]] = {}

def register(name: str):
    def decorator(cls: type[BaseAgent]) -> type[BaseAgent]:
        _REGISTRY[name] = cls
        return cls
    return decorator

def get_agent(name: str, **deps) -> BaseAgent:
    if name not in _REGISTRY:
        raise UnknownAgentError(f"No agent registered for '{name}'")
    return _REGISTRY[name](**deps)

def list_agents() -> list[str]:
    return list(_REGISTRY.keys())
```

Each agent module calls `@register("research")` on its agent class. The registry
is populated when the module is imported. The `api/app.py` lifespan imports all
agent modules once at startup to trigger registration.

## Base Agent Interface

`ze/agents/base.py`

```python
from abc import ABC, abstractmethod
from ze.agents.types import AgentResult, AgentContext

class BaseAgent(ABC):
    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
```

## Shared Types

`ze/agents/types.py`

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class ToolCall:
    tool_name:   str
    args:        dict[str, Any]
    result:      Any
    duration_ms: int
    success:     bool
    error:       str | None = None

@dataclass
class AgentContext:
    prompt: str
    agent: str
    intent: str
    memory: MemoryContext       # from ze/memory/types.py
    session_id: str

@dataclass
class AgentResult:
    agent: str
    output: str
    tool_calls: list[ToolCall]
    requires_confirmation: bool
    draft_content: str | None           # populated for draft_only gate decisions
    memory_proposals: list[UserFact]    # may be empty; never None
```

## Per-Agent Definitions

Each agent's non-code config lives in `config/agents/<name>.yaml`.

```yaml
# Example: config/agents/research.yaml
enabled: true
description: |
  Handles web searches, fact-finding, summarisation, and research synthesis.
  Use for questions about current events, factual lookups, topic deep-dives,
  or anything requiring information retrieval from the web.
model: anthropic/claude-sonnet-4-5
tools: [web_search, summarize, extract_facts]
timeout_seconds: 30
intent_map:
  read: web_search    # pipeline: web_search → summarize
```

---

### `calendar` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-haiku-4-5` |
| Tools    | `read_events`, `create_event`, `update_event`, `delete_event` |
| Scope    | Google Calendar API (Phase 3) |
| Phase    | 3 |

**Intent map:**

| Intent   | Tool           |
|----------|----------------|
| `read`   | `read_events`  |
| `create` | `create_event` |
| `update` | `update_event` |
| `delete` | `delete_event` |

**Notes:** All write tools (`create`, `update`, `delete`) require capability gate
to pass before execution. Auth via Google OAuth2 — token stored in Fly.io secrets.

---

### `email` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-haiku-4-5` |
| Tools    | `read_emails`, `draft_email`, `send_email`, `archive_email` |
| Scope    | Gmail API (Phase 3) |
| Phase    | 3 |

**Intent map:**

| Intent   | Tool            | Note |
|----------|-----------------|------|
| `read`   | `read_emails`   |      |
| `create` | `draft_email`   | `send_email` only invoked after gate EXECUTE |
| `update` | `draft_email`   |      |
| `delete` | `archive_email` | Hard delete not supported |

---

### `research` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-sonnet-4-5` |
| Tools    | `web_search`, `summarize`, `extract_facts` |
| Scope    | Tavily API |
| Phase    | 1 |

**Intent map:**

| Intent | Tool pipeline |
|--------|---------------|
| `read` | `web_search` → `summarize` (always sequential, not branching) |

**Notes:**
- Uses Tavily API for structured search results (title, URL, snippet, score).
- `extract_facts` is called by the agent to propose `memory_proposals`.
- Tavily API key stored in `.env` as `TAVILY_API_KEY`.

---

### `workflow` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-sonnet-4-5` |
| Tools    | `run_script`, `call_api`, `move_file`, `send_notification` |
| Scope    | Configured integrations only (Phase 4) |
| Phase    | 4 |

**Intent map:** LLM-determined (tool selection is too variable for a keyword map).

---

### `companion` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-sonnet-4-5` |
| Tools    | None — pure reasoning, no external calls |
| Scope    | In-context only |
| Phase    | 1 |

**Intent map:**

| Intent  | Tool |
|---------|------|
| `reason`| Direct LLM completion via `OpenRouterClient.stream()` |

**Notes:**
- Receives full `MemoryContext` — user facts and recent episodes.
- `memory_proposals` always empty (companion makes no tool calls that produce facts).
- `tool_calls` always empty list.

## Per-Agent Module Structure

```
ze/agents/<name>/
├── __init__.py
├── agent.py        # @register("<name>") class, implements BaseAgent
├── prompt.py       # System prompt string(s) — no inline strings in agent.py
├── tools.py        # Async tool functions called by the agent
└── intent_map.py   # Dict[str, Callable] mapping intent → tool function
```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze.agents.base` | `BaseAgent` ABC |
| `ze.agents.registry` | `@register` decorator |
| `ze.agents.types` | `AgentResult`, `AgentContext`, `ToolCall` |
| `ze.memory.types` | `UserFact`, `MemoryContext` |
| `ze.openrouter.client` | `OpenRouterClient` for LLM calls |
| `ze.errors` | `AgentError`, `ToolError`, `UnknownAgentError` |
| `ze.logging` | Structured logging per tool call |

## Implementation Notes

- Every `run()` call must return `AgentResult`, even on partial failure.
  Set `output` to an error summary, `tool_calls` to whatever completed,
  `memory_proposals` to empty list.
- Tool timing: wrap every tool call in a `time.monotonic()` pair and populate
  `ToolCall.duration_ms`.
- Tool errors: catch exceptions inside tool functions, set `ToolCall.success=False`
  and `ToolCall.error=str(e)`. Re-raise only if the error is unrecoverable.
- System prompts must include explicit statements of what the agent cannot do.
  This reduces hallucinated tool calls outside the registry.
- `AgentContext.memory` is always populated, even for Phase 1 agents (it will be
  empty `MemoryContext` until Phase 2 memory system is live).

## Open Questions

- [ ] Phase 3: Google OAuth2 token refresh strategy — confirm short-lived access
  token + long-lived refresh token stored as Fly.io secret. Refresh on 401 response.
- [ ] Phase 4: Workflow integrations to define (Notion, GitHub, Slack, or other).
