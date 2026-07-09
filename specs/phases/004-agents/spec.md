# Agents — Spec

> **Status:** Deprecated — superseded by [`core/01-agent.md`](../core/01-agent.md)
>
> This spec describes the original YAML-based agent registration pattern
> (`@register("name")`, `intent_map.py`, per-agent YAML config files). The current
> implementation uses the `@agent` decorator with class attributes. See
> `core/01-agent.md` for the authoritative spec.

---

## Purpose

Define the five sub-agents of Ze. Each agent is an isolated module with its own
system prompt, tool registry, model config, and intent→tool map. Agents are
registered via a decorator and discovered dynamically — the orchestration layer
never imports individual agent modules directly.

## Responsibilities (all agents)

- Implement the `BaseAgent` interface.
- Register with `@register("<name>")` in `agents/registry.py`.
- Own agent-specific instructions in a module-level `_AGENT_INSTRUCTIONS` constant at the top of `agent.py`.
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
tools: [web_search, summarize]
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
| Tools    | `web_search`, `summarize` |
| Scope    | Tavily API |
| Phase    | 1 |

**Intent map:**

| Intent | Tool pipeline |
|--------|---------------|
| `read` | `web_search` → `summarize` (always sequential, not branching) |

**Notes:**
- Uses Tavily API for structured search results (title, URL, snippet, score).
- User facts are extracted in `write_memory` (see `specs/zc-06-memory.md`), not by agent tools.
- Tavily API key stored in `.env` as `TAVILY_API_KEY`.

---

### `workflow` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-sonnet-4-5` |
| Tools    | None — actions are internal methods, not globally registered tools |
| Scope    | Workflow lifecycle management (Phase 4) |
| Phase    | 4 |

**Role:** Manager only — creates, lists, enables, disables, deletes, and triggers stored
workflows. Never executes workflow steps directly; execution is handled by the workflow
graph in `ze/orchestration/workflow_graph.py`.

**Intent map:**

| Intent   | Capability |
|----------|------------|
| `read`   | autonomous |
| `manage` | confirm    |

---

### `companion` Agent

| Property | Value |
|----------|-------|
| Model    | `anthropic/claude-sonnet-4-5` |
| Tools    | `extract_contacts`, `log_outreach_event` (post-response); no web/calendar/email tools |
| Scope    | In-context only |
| Phase    | 1 |

**Intent map:**

| Intent  | Tool |
|---------|------|
| `reason`| Direct LLM completion via `OpenRouterClient.stream()` |

**Notes:**
- Receives full `MemoryContext` — user facts and recent episodes.
- User facts are proposed by `write_memory` extraction, not by companion tools.
- Post-response tools: `extract_contacts`, optional `log_outreach_event`.

## Per-Agent Module Structure

```
ze/agents/<name>/
├── __init__.py
├── agent.py        # _AGENT_INSTRUCTIONS constant + @register class, implements BaseAgent
└── tools.py        # Async tool functions called by the agent
```

Intent→permission mappings live in `config/agents/<name>.yaml:intent_map` (YAML)
and are validated at startup against `config/capabilities.yaml`. There is no
per-agent Python `intent_map.py` — that would be a duplicate of the YAML.

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

- [x] Phase 3: Google OAuth2 — refresh token in `GOOGLE_REFRESH_TOKEN` Fly.io
  secret, access token exchanged at startup and refreshed on 401. Single OAuth2
  flow run once via local CLI script. Covers both Calendar and Gmail.
- [x] Phase 4: Workflow manager agent implemented. Execution delegated to the
  workflow graph (see `12-workflow.md`). Dynamic plan approval flow not yet started.
