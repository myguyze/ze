# ze-agents

Developer API for Ze — agent execution primitives, shared types, and harness hooks. Plugin authors reach this package through `ze-sdk`, not by importing `ze_agents` directly.

## Responsibilities

| Module | What it provides |
|---|---|
| `base_agent.py` | `BaseAgent` ABC with the agentic ReAct loop |
| `registry.py` | `@agent` decorator and `AgentRegistry` |
| `tool.py` | `@tool` decorator and `ToolAccess` |
| `client.py` | `LLMClient` Protocol |
| `db.py` | `DBPool` Protocol |
| `settings.py` | `Settings` dataclass |
| `errors.py` | Full `ZeError` hierarchy |
| `hooks.py` | `HarnessHook` ABC for agentic-loop interception |
| `interface/` | `AppInterface` ABC, `InputPreprocessor`, validation, types |
| `progress/` | `ProgressReporter`, locale-key translations |
| `delegate.py` | Multi-agent handoff helpers |
| `tasks.py` | Background task utilities |
| `types.py` | Shared domain types (`Mode`, etc.) |

## Dependencies

```mermaid
graph LR
    agents[ze-agents] --> onboarding[ze-onboarding]
```

No other Ze package dependencies. Third-party: `structlog`, `pyyaml`, `typing_extensions`.

## Usage

Consumed by `ze-plugin`, `ze-core`, and re-exported via `ze-sdk`. Engine and plugin bootstrap code import directly:

```python
from ze_agents.registry import agent
from ze_agents.base_agent import BaseAgent
from ze_agents.tool import tool
```

## Testing

From the repo root:

```bash
make test-agents
```

See [docs/testing.md](../../docs/testing.md).
