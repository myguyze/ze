# ze-core

Pure infrastructure package for Ze. Contains no personal-assistant domain logic — only the framework primitives shared by all other packages.

## Responsibilities

| Module | What it provides |
|---|---|
| `orchestration/` | `BaseAgent`, `@agent`, `@tool`, `agent_registry`, `graph_builder`, `AgentState`, graph nodes |
| `routing/` | `EmbeddingRouter`, `ComplexityEstimator`, `PostgresRoutingStore`, fallback logic |
| `memory/` | `PostgresMemoryStore`, `MemoryConsolidator`, extractor, types |
| `capability/` | `CapabilityGate`, `PostgresCapabilityOverrideStore`, permission modes |
| `channels/` | `Channel` ABC, `ChannelRegistry`, types |
| `interface/` | `AppInterface` ABC, `InputPreprocessor`, validation, types |
| `openrouter/` | `OpenRouterClient`, streaming, types |
| `proactive/` | `ProactiveScheduler`, `ProactiveNotifier`, `ProactiveJob`, `PushLogStore` |
| `progress/` | `ProgressReporter`, locale-key translations |
| `telemetry/` | `CostTracker`, `CostReconciler`, `PostgresCostStore`, context var |
| `messages/` | `MessageStore`, message types |
| `conversation.py` | `invoke_raw_turn`, `resume_turn` entry points |
| `plugin.py` | `ZePlugin` ABC — container and graph extension seam |
| `container.py` | Base `Container` with DI wiring |
| `embeddings.py` | Shared `paraphrase-multilingual-MiniLM-L12-v2` singleton |

## Dependencies

No Ze package dependencies. Depends only on: `langgraph`, `asyncpg`, `openai`, `sentence-transformers`, `structlog`, `pydantic`.

## Usage

This package is not used directly by application code — it is consumed by `ze-personal`, `ze-calendar`, `ze-news`, and `ze-api`.

```python
from ze_core.orchestration.registry import agent, get_agent
from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.tool import tool
from ze_core.plugin import ZePlugin
```

## Testing

```bash
make test-core
# or
uv run pytest core/ze-core/tests -q
```
