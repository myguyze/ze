# Cost-Aware Model Selection — Spec

## Purpose

Reduce LLM spend by routing simple requests to a cheaper model tier while
preserving full-quality responses for complex tasks. The classifier runs
entirely in-process — no extra LLM call, zero added latency. Agents that
have a `model_simple` tier configured in `config/config.yaml` opt in
automatically; all others are unaffected.

## Design Principles

- **Default to quality.** Any ambiguity in the complexity signal resolves to
  the primary (expensive) model. The classifier must be confident before
  downgrading.
- **Invisible to agents.** Agents receive the selected model via `AgentContext`
  and call `self._model(ctx)` as always — no agent needs to know about
  complexity classification.
- **Observable.** Every routing decision logs `complexity` and `model_selected`.
  Cost telemetry already captures the model used; correlating the two tables
  makes savings measurable.
- **Opt-in per agent.** Only agents that configure `model_simple` participate.
  Agents that already run Haiku (calendar, email) simply omit the field.

## Out of Scope

- Per-session or per-user model overrides.
- Three-tier (simple/medium/complex) selection.
- Budget caps or real-time cost alerting.
- Applying to system flows (synthesis, memory, insights, router) — those
  already use Haiku.
- Retroactive reclassification of historical requests.

---

## New Module: `ze/routing/complexity.py`

```python
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ComplexityResult:
    complexity: str  # "simple" | "complex"
    score: int       # negative = simple evidence; positive = complex evidence


class ComplexityEstimator:
    """Pure-function classifier. No I/O. No LLM calls."""

    _COMPLEX_PATTERNS = re.compile(
        r"\b("
        r"explain why|analyz[ei]|analys[ei]|compar[ei]"
        r"|why does|why do|how does|how do"
        r"|help me (understand|think|reason|decide)"
        r"|synthesiz[ei]|synthes[ei]s"
        r"|should i|should we"
        r"|evaluat[ei]|assess"
        r"|implication|trade.?off|pros and cons"
        r"|deep dive|walk me through|think through|brainstorm"
        r"|critically|in depth|in detail"
        r")\b",
        re.IGNORECASE,
    )

    _SIMPLE_PATTERNS = re.compile(
        r"\b("
        r"what is|what's the|what are"
        r"|who is|who's the"
        r"|when did|when was|when is"
        r"|where is|where was"
        r"|define|definition of"
        r"|how many|how much"
        r"|list the|give me a list|list of"
        r")\b",
        re.IGNORECASE,
    )

    def classify(self, prompt: str, intent: str, confidence: float) -> str:
        score = 0

        # Word count
        word_count = len(prompt.split())
        if word_count > 30:
            score += 2
        elif word_count < 12:
            score -= 1

        # Intent
        if intent == "reason":
            score += 2

        # Keyword matches (each pattern list capped at ±4)
        complex_hits = len(self._COMPLEX_PATTERNS.findall(prompt))
        simple_hits = len(self._SIMPLE_PATTERNS.findall(prompt))
        score += min(complex_hits * 2, 4)
        score -= min(simple_hits * 2, 4)

        # High routing confidence is a weak simple signal
        if confidence > 0.80:
            score -= 1

        complexity = "simple" if score < -1 else "complex"
        return complexity
```

`ComplexityEstimator` is stateless and injected into `EmbeddingRouter` as a
constructor argument. It is constructed once in `build_container()`.

---

## Changes to `ze/routing/types.py`

Add `model: str` to `SubTask` and `complexity: str` to `RoutingEnvelope`.

```python
@dataclass
class SubTask:
    agent: str
    intent: str
    prompt: str
    model: str          # resolved by EmbeddingRouter; passed through to AgentContext

@dataclass
class RoutingEnvelope:
    primary_agent: str
    confidence: float
    score_gap: float
    routing_method: str
    is_compound: bool
    subtasks: list[SubTask]
    requires_synthesis: bool
    raw_scores: dict[str, float]
    complexity: str     # "simple" | "complex" — set for primary subtask
```

For compound tasks the complexity label is derived from the primary subtask
(the one with the highest score). Each subtask still carries its own resolved
`model`.

---

## Changes to `ze/routing/router.py`

`EmbeddingRouter.__init__` accepts `estimator: ComplexityEstimator`.

Add a private helper:

```python
def _resolve_model(self, agent: str, complexity: str) -> str:
    cfg = self._settings.agent_configs.get(agent, {})
    if complexity == "simple" and "model_simple" in cfg:
        return cfg["model_simple"]
    return cfg.get("model", "anthropic/claude-sonnet-4-5")
```

In `_score_and_route`, after the top agent and intent are known:

```python
complexity = self._estimator.classify(prompt, intent, top_score)
model = self._resolve_model(top_agent, complexity)
subtask = SubTask(agent=top_agent, intent=intent, prompt=prompt, model=model)
```

For the Haiku fallback path, `decompose()` already returns subtasks without a
model field. After `decompose()` returns the envelope, the router resolves a
model for each subtask independently using the same `_resolve_model()` call,
using the complexity derived from the full (original) prompt and the primary
subtask's intent.

Update `_write_log` to include `complexity` and `model_selected`:

```python
await conn.execute(
    """
    INSERT INTO routing_log
        (session_id, prompt, method, primary_agent,
         confidence, score_gap, is_compound, raw_scores,
         complexity, model_selected)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)
    """,
    session_id, prompt, envelope.routing_method, envelope.primary_agent,
    envelope.confidence, envelope.score_gap, envelope.is_compound,
    json.dumps(envelope.raw_scores),
    envelope.complexity,
    envelope.subtasks[0].model if envelope.subtasks else None,
)
```

---

## Changes to `ze/agents/types.py`

```python
@dataclass
class AgentContext:
    session_id: str
    prompt: str
    intent: str
    gate_decision: GateDecision = GateDecision.EXECUTE
    memory: MemoryContext = field(default_factory=MemoryContext)
    tool_calls: list[ToolCall] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    model: str | None = None    # None → agent falls back to its config default
```

---

## Changes to `ze/agents/base.py`

Update `_model()` to accept and prefer the context model:

```python
def _model(self, ctx: AgentContext | None = None) -> str:
    if ctx is not None and ctx.model is not None:
        return ctx.model
    return self._settings.agent_configs.get(self.name, {}).get(
        "model", "anthropic/claude-sonnet-4-5"
    )
```

All call sites in every agent's `run()` and `stream()` methods update from
`self._model()` to `self._model(ctx)`. There are ~13 call sites across 5
agents.

---

## Changes to `ze/orchestration/nodes/execution.py`

In `_execute_single`, `_execute_compound`, and `draft_response`, pass
`model=subtask.model` when constructing `AgentContext`:

```python
ctx = AgentContext(
    session_id=base_ctx.session_id,
    prompt=subtask.prompt,
    intent=subtask.intent,
    gate_decision=gate_decision,
    memory=base_ctx.memory,
    model=subtask.model,
)
```

---

## Configuration

Add `model_simple` to agents that should participate. Only `research` and
`companion` are eligible — they are the only agents using Sonnet for user-facing
requests. Workflow planning is structurally complex (always multi-step
reasoning); calendar and email already run Haiku.

```yaml
# config/config.yaml

agents:
  research:
    model: anthropic/claude-sonnet-4-5
    model_simple: anthropic/claude-haiku-4-5
    # ... rest unchanged

  companion:
    model: anthropic/claude-sonnet-4-5
    model_simple: anthropic/claude-haiku-4-5
    # ... rest unchanged
```

---

## Database Migration — 009

File: `migrations/versions/009_routing_complexity.py`

```sql
-- upgrade
ALTER TABLE routing_log
    ADD COLUMN IF NOT EXISTS complexity     TEXT,
    ADD COLUMN IF NOT EXISTS model_selected TEXT;

-- downgrade
ALTER TABLE routing_log
    DROP COLUMN IF EXISTS complexity,
    DROP COLUMN IF EXISTS model_selected;
```

Columns are nullable — historical rows are unaffected.

---

## Container Changes

`ComplexityEstimator` is stateless; construct it once in `build_container()`
and inject it into `EmbeddingRouter`:

```python
estimator = ComplexityEstimator()
router = EmbeddingRouter(
    embedder=embedder,
    openrouter_client=openrouter_client,
    db_pool=pool,
    settings=settings,
    estimator=estimator,
)
```

---

## Testing

### `ComplexityEstimator.classify()`

Cover each signal path and their interactions:

| Case | Expected |
|------|----------|
| Short factual prompt, high confidence, simple keyword | `"simple"` |
| Long analytical prompt, complex keyword | `"complex"` |
| Intent `"reason"` with short prompt | `"complex"` (intent overrides length) |
| No signals, medium length, no keywords | `"complex"` (default) |
| Mixed signals (1 simple, 1 complex keyword) | `"complex"` (tie → complex) |
| Borderline score = -1 | `"complex"` (threshold is strict `< -1`) |
| Score = -2 | `"simple"` |

### `EmbeddingRouter.route()`

- Mock `ComplexityEstimator.classify()` returning `"simple"` for an agent
  with `model_simple` configured → assert `subtask.model == model_simple`.
- Mock returning `"complex"` → assert `subtask.model == primary model`.
- Agent without `model_simple` → assert `subtask.model == primary model`
  regardless of complexity.
- Assert `routing_log` write includes `complexity` and `model_selected`.

### `BaseAgent._model()`

- `ctx.model = "anthropic/claude-haiku-4-5"` → returned.
- `ctx.model = None` → falls back to agent config.
- `ctx = None` → falls back to agent config.

### Integration: `AgentContext.model` propagation

In `_execute_single`, assert that `AgentContext.model` equals `subtask.model`.

---

## Observability

Savings are measurable immediately after deploy:

```sql
-- models selected per agent over last 7 days
SELECT primary_agent, model_selected, complexity, COUNT(*)
FROM routing_log
WHERE created_at > NOW() - INTERVAL '7 days'
  AND model_selected IS NOT NULL
GROUP BY primary_agent, model_selected, complexity
ORDER BY primary_agent, COUNT(*) DESC;

-- correlate with actual cost
SELECT rl.model_selected, rl.complexity,
       SUM(lc.total_tokens) AS tokens,
       SUM(lc.cost_usd)     AS cost_usd
FROM routing_log rl
JOIN llm_cost_log lc
  ON lc.session_id = rl.session_id
 AND lc.model = rl.model_selected
WHERE rl.created_at > NOW() - INTERVAL '7 days'
GROUP BY rl.model_selected, rl.complexity;
```

---

## Open Questions

All resolved.
