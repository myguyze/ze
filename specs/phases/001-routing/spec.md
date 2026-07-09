# Routing — Spec

## Purpose

Route incoming user prompts to the correct sub-agent using local
sentence-transformer embeddings. Fall back to Haiku via OpenRouter for ambiguous
or compound prompts. Zero LLM calls in the happy path.

## Responsibilities

- Load and encode agent definitions from `config/agents/<name>.yaml` at startup.
- Encode incoming prompts at runtime using the shared `SentenceTransformer` instance
  from `ze/embeddings.py` (never load a second model instance).
- Compute cosine similarity scores between the prompt embedding and all agent
  definition embeddings.
- Apply confidence threshold and gap threshold to decide routing outcome.
- Detect compound tasks via a low gap score between the top two agents.
- Delegate to `haiku_fallback.py` when below threshold or compound.
- Return a `RoutingEnvelope` for all downstream consumers.
- Write every routing decision to the `routing_log` Postgres table.

## Out of Scope

- Does not execute any agent logic.
- Does not fetch memory context.
- Does not check capability permissions.
- Does not construct `AgentContext`.

## Interface Contract

### Input

```python
prompt: str  # raw user message, already stripped of whitespace
```

### Output

```python
RoutingEnvelope  # see Data Structures
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Empty or whitespace-only prompt | Raise `InvalidPromptError` |
| All scores below `ROUTING_THRESHOLD` | Force Haiku fallback |
| Gap below `GAP_THRESHOLD` | Treat as compound, force Haiku decomposition |
| Single enabled agent in registry | Route directly, skip scoring |
| Haiku decomposition fails twice | Raise `RoutingError` with original prompt |
| Agent name from Haiku not in registry | Raise `RoutingError`, log unknown agent name |

## Data Structures

Lives in `ze/routing/types.py`.

```python
from dataclasses import dataclass, field

@dataclass
class SubTask:
    agent: str       # must match a registered agent name
    intent: str      # "read" | "create" | "update" | "delete" | "execute" | "reason"
    prompt: str      # isolated prompt for this subtask only

@dataclass
class RoutingEnvelope:
    primary_agent: str
    confidence: float          # top cosine score (0–1)
    score_gap: float           # scores[0] - scores[1]; 0 if only one agent
    routing_method: str        # "embedding" | "haiku"
    is_compound: bool
    subtasks: list[SubTask]    # populated by Haiku; exactly one entry for non-compound
    requires_synthesis: bool   # true when len(subtasks) > 1
    raw_scores: dict[str, float]  # all agent scores, for logging
```

Note: `intent` lives only on `SubTask`, not on `RoutingEnvelope`. For non-compound
routing, `subtasks` contains a single `SubTask` with the resolved intent.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze.embeddings` | Shared `SentenceTransformer` instance |
| `ze.openrouter.client` | `OpenRouterClient` for Haiku fallback |
| `ze.db` | asyncpg pool for writing to `routing_log` |
| `ze.errors` | `InvalidPromptError`, `RoutingError` |
| `ze.settings` | Threshold values, Haiku model name |

## Configuration

Read from `config/models.yaml`:

```yaml
routing:
  threshold: 0.55        # minimum score to route confidently
  gap_threshold: 0.10    # minimum spread between top two agents
  embedding_model: paraphrase-multilingual-MiniLM-L12-v2
  fallback_model: anthropic/claude-haiku-4-5
```

Agent definitions loaded from `config/agents/<name>.yaml` — the `description` field
is the text that is embedded. All enabled agents are loaded; disabled agents
(those missing from the directory or explicitly `enabled: false`) are excluded.

## Database Schema

```sql
CREATE TABLE routing_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    method      TEXT NOT NULL,       -- 'embedding' | 'haiku'
    primary_agent TEXT NOT NULL,
    confidence  FLOAT,
    score_gap   FLOAT,
    is_compound BOOLEAN NOT NULL DEFAULT FALSE,
    raw_scores  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON routing_log (session_id);
CREATE INDEX ON routing_log (created_at DESC);
```

## Implementation Notes

- Use `normalize_embeddings=True` in `SentenceTransformer.encode()` so cosine
  similarity reduces to a dot product.
- Agent embeddings are encoded once at startup and cached in memory. If
  `config/agents/` changes on disk, the server must restart (no hot-reload for
  embeddings — the cost of re-encoding is low at startup but high per-request).
- Score gap = `sorted_scores[0] - sorted_scores[1]` after descending sort.
- Haiku decomposition prompt must request strict JSON. Wrap in `try/except` and
  retry once before raising `RoutingError`.
- Haiku response format expected:

```json
{
  "subtasks": [
    { "agent": "calendar", "intent": "read", "prompt": "..." },
    { "agent": "email", "intent": "create", "prompt": "..." }
  ]
}
```

- The routing log write must not block the main flow. Fire it as an asyncio task
  (`asyncio.create_task`) so a slow DB write does not add latency to the response.
- `EmbeddingRouter` is a class injected with its dependencies. Do not use
  module-level globals.

```python
class EmbeddingRouter:
    def __init__(
        self,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        db_pool: asyncpg.Pool,
        settings: Settings,
    ): ...

    async def route(self, prompt: str, session_id: str) -> RoutingEnvelope: ...
```

## Open Questions

All resolved.
