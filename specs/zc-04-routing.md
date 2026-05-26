# Ze Core — Routing — Spec

## Purpose

Select which agent (or agents) should handle a user prompt. The router is the
first node the orchestration graph executes after input normalisation. It
produces a `RoutingEnvelope` that names all subtasks and their resolved models.
Routing is fully deterministic for high-confidence prompts (embedding cosine
similarity) and falls back to a small LLM for low-confidence or multi-agent
cases.

---

## Responsibilities

- Embed the user prompt and compute cosine similarity against all enabled agent
  descriptions.
- Return a `RoutingEnvelope` with one or more `SubTask` entries.
- Fall back to a small LLM (`haiku_fallback`) when embedding confidence is low
  or the gap between top two scores is narrow.
- Classify each subtask as `"simple"` or `"complex"` and resolve the correct
  model (`model` vs `model_simple`) from the agent class.
- Log each routing decision asynchronously (fire-and-forget).

## Out of Scope

- Does not evaluate capability modes (that is the gate's job).
- Does not execute agents.
- Does not load agent descriptions from a config file — reads from the agent
  registry populated by `@agent`.
- Does not choose tools.

---

## Data Structures

`ze_core/routing/types.py`

```python
@dataclass
class SubTask:
    agent: str    # registered agent name, e.g. "calendar"
    intent: str   # "read" | "create" | "update" | "delete" | "execute" | "reason"
    prompt: str   # isolated prompt for this subtask only
    model: str = ""  # resolved by EmbeddingRouter; passed through to AgentContext


@dataclass
class RoutingEnvelope:
    primary_agent: str
    confidence: float         # top cosine score (0–1)
    score_gap: float          # scores[0] - scores[1]; 0.0 for single-agent or haiku
    routing_method: str       # "embedding" | "haiku" | "haiku_fallback"
    is_compound: bool
    subtasks: list[SubTask]   # always at least one entry
    requires_synthesis: bool  # True when len(subtasks) > 1 and not sequential
    raw_scores: dict[str, float] = field(default_factory=dict)
    is_sequential: bool = False  # True when step N's output feeds step N+1
    complexity: str = "complex"  # "simple" | "complex" — set for primary subtask
```

`RoutingEnvelope.subtasks` always has at least one entry. An empty list is
never valid and indicates a bug in the haiku fallback.

---

## EmbeddingRouter

`ze_core/routing/router.py`

### Constructor

```python
class EmbeddingRouter:
    def __init__(
        self,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        db_pool: asyncpg.Pool,
        settings: Settings,
        estimator: ComplexityEstimator | None = None,
    ) -> None:
```

On construction, the router calls `_load_agent_embeddings()` which reads all
enabled agents from the registry and encodes their `description` strings into a
matrix. This is the only time embeddings are computed; the matrix is cached for
the lifetime of the container.

### Agent source

The router reads directly from the agent registry — **not from a config file**.

```python
from ze_core.orchestration.registry import get_enabled_agents

def _load_agent_embeddings(self) -> None:
    enabled = get_enabled_agents()   # dict[str, type[BaseAgent]]
    if not enabled:
        raise RoutingError("No enabled agents found")
    self._agent_names = sorted(enabled.keys())
    descriptions = [enabled[n].description.strip() for n in self._agent_names]
    self._agent_matrix = self._embedder.encode(descriptions)
```

Sorted order is deterministic across restarts — important for test fixtures.

### `route()` — main entry point

```python
async def route(self, prompt: str, session_id: str) -> RoutingEnvelope:
```

1. Reject empty or whitespace-only prompts with `InvalidPromptError`.
2. If only one enabled agent exists, return a single-agent envelope immediately
   (no embedding computation needed).
3. Otherwise call `_score_and_route(prompt)`.
4. Fire-and-forget: `asyncio.create_task(self._write_log(session_id, prompt, envelope))`.
5. Return the envelope.

### Scoring and threshold logic

```python
async def _score_and_route(self, prompt: str) -> RoutingEnvelope:
```

1. Embed the prompt.
2. Compute cosine similarity via dot product (embeddings are unit-normalised):
   `scores = agent_matrix @ prompt_vec`.
3. Sort descending; extract `top_agent`, `top_score`, `score_gap`.
4. Compare against `routing.threshold` and `routing.gap_threshold` from settings.
5. If either threshold is missed → call `haiku_fallback.decompose()`.
6. Otherwise → return a single-subtask `RoutingEnvelope` with method `"embedding"`.

### Thresholds (settings)

| Key | Default | Meaning |
|---|---|---|
| `routing.threshold` | `0.55` | Minimum top score to trust embedding |
| `routing.gap_threshold` | `0.10` | Minimum gap between top two scores |
| `routing.fallback_model` | `"anthropic/claude-haiku-4-5"` | Model used by haiku fallback |

### Model resolution

After routing, the resolved model is written to each `SubTask.model`:

```python
def _resolve_model(self, agent_cls: type[BaseAgent], complexity: str) -> str:
    if complexity == "simple" and agent_cls.model_simple:
        return agent_cls.model_simple
    return agent_cls.model
```

Model is never left empty in the returned envelope.

### Primary intent

```python
def _primary_intent(self, agent_cls: type[BaseAgent]) -> str:
    return next(iter(agent_cls.intent_map), "read")
```

The first key in `intent_map` is the agent's primary intent. If `intent_map` is
empty, `"read"` is used as a safe default.

---

## Haiku Fallback

`ze_core/routing/haiku_fallback.py`

Called when embedding scores are ambiguous. Sends the prompt to a small LLM
(`fallback_model`) with the list of enabled agent descriptions and a structured
instruction to return a JSON decomposition.

### Input

```python
async def decompose(
    prompt: str,
    raw_scores: dict[str, float],
    client: OpenRouterClient,
    agent_registry: dict[str, type[BaseAgent]],  # get_enabled_agents() result
    fallback_model: str,
    logger: structlog.BoundLogger | None = None,
) -> RoutingEnvelope:
```

Note: Ze Core passes the agent registry dict directly instead of `Settings`.
The system prompt is built from `agent_cls.description` values.

### Retry and error handling

- Retried once on JSON parse failure.
- If both attempts fail: falls back to the first enabled agent with `intent_map`
  key `"reason"`, or the first enabled agent if none has `"reason"`. Logs
  `haiku_fallback_exhausted`. Sets `routing_method = "haiku_fallback"`.
- If Haiku returns an unknown agent name: raises `RoutingError` immediately
  (no retry) — this indicates a prompt injection or a stale agent list.

### Output schema expected from LLM

```json
{
  "subtasks": [
    { "agent": "<name>", "intent": "<intent>", "prompt": "<isolated prompt>" }
  ],
  "sequential": false
}
```

- `subtasks` must be non-empty; an empty array is treated as a parse failure.
- `sequential: true` means step N's output feeds step N+1 as input.
  `requires_synthesis` is `False` for sequential tasks (the final subtask
  incorporates all prior results).

---

## ComplexityEstimator

`ze_core/routing/complexity.py`

Pure function. No I/O. No LLM calls. Classifies a prompt as `"simple"` or
`"complex"` based on word count, intent, keyword patterns, and routing
confidence.

```python
class ComplexityEstimator:
    def classify(self, prompt: str, intent: str, confidence: float) -> str:
        ...
        return "simple" | "complex"
```

### Scoring rules

| Signal | Score delta |
|---|---|
| Word count > 30 | +2 |
| Word count < 12 | −1 |
| Intent is `"reason"` | +2 |
| Complex keyword match (each, capped at +4) | +2 |
| Simple keyword match (each, capped at −4) | −2 |
| Routing confidence > 0.80 | −1 |

Final: `score < -1` → `"simple"`, else `"complex"`.

---

## Routing Log

Each routing decision is persisted asynchronously to the `routing_log` table.
This is fire-and-forget — a write failure is logged as a warning but never
propagates to the caller.

```sql
CREATE TABLE routing_log (
    id           BIGSERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id   TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    method       TEXT NOT NULL,     -- "embedding" | "haiku" | "haiku_fallback"
    primary_agent TEXT NOT NULL,
    confidence   FLOAT,
    score_gap    FLOAT,
    is_compound  BOOLEAN,
    raw_scores   JSONB,
    complexity   TEXT,
    model_selected TEXT
);
```

---

## Usage in the Orchestration Graph

The router is called in the `embed_route` node:

```python
async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    router: EmbeddingRouter = config["configurable"]["router"]
    envelope = await router.route(
        prompt=state["prompt"],
        session_id=state["session_id"],
    )
    return {"envelope": envelope}
```

The `envelope` drives all downstream routing decisions:
- `envelope.is_compound` → whether the graph fans out to multiple agents.
- `envelope.subtasks[0]` → primary agent and intent for the capability check.
- `envelope.requires_synthesis` → whether a synthesis node is needed after
  all subtasks complete.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.orchestration.registry` | `get_enabled_agents()` — reads descriptions, intent_map, model |
| `ze_core.routing.types` | `SubTask`, `RoutingEnvelope` |
| `ze_core.routing.haiku_fallback` | LLM-based decomposition |
| `ze_core.routing.complexity` | `ComplexityEstimator` |
| `ze_core.errors` | `InvalidPromptError`, `RoutingError` |
| `ze_core.logging` | Structured logging |
| `sentence_transformers` | Embedding model (injected, not imported directly) |
| `asyncpg` | Routing log write |

---

## Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| Empty prompt | `InvalidPromptError` |
| No enabled agents | `RoutingError` at router construction |
| Only one enabled agent | Return single-subtask envelope, skip scoring |
| Top score below threshold | Haiku fallback |
| Score gap below gap_threshold | Haiku fallback |
| Haiku returns unknown agent | `RoutingError` (immediate, no retry) |
| Haiku returns empty subtasks | Retry once; then hard fallback to first `"reason"` agent |
| Haiku fails twice | Hard fallback; `routing_method = "haiku_fallback"` |
| Routing log write fails | Log warning, ignore — never propagates |
