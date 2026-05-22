import json

import structlog

from ze.errors import RoutingError
from ze.openrouter.client import OpenRouterClient
from ze.routing.types import RoutingEnvelope, SubTask
from ze.settings import Settings

_SYSTEM_PROMPT = """\
You are a routing assistant for Ze, a personal AI assistant.
Analyze the user prompt and decide which agent(s) should handle it.

Available agents:
{agent_descriptions}

Respond ONLY with a JSON object — no prose, no markdown:
{{
  "subtasks": [
    {{ "agent": "<name>", "intent": "<intent>", "prompt": "<isolated prompt>" }}
  ],
  "sequential": false
}}

Intent values: read, create, update, delete, execute, reason
- ALWAYS return at least one subtask. An empty subtasks array is never valid.
- When the user says "research", "look up", "find", "search", or asks about facts/news/history, use the research agent.
- When uncertain and no research or tool use is needed, default to the companion agent with intent "reason".
- Use exactly one subtask for single-agent tasks.
- Use multiple subtasks only when the request genuinely requires different agents.
- Each subtask prompt must be self-contained for its agent.
- Set "sequential" to true when step N's output is needed as input for step N+1 (data dependency). Set to false for independent parallel tasks.
"""


def _extract_json_object(raw: str) -> str:
    """Extract the first top-level JSON object from raw text.

    Handles markdown code fences, leading prose, and any trailing text or
    second JSON blocks that cause json.loads to raise 'Extra data'.
    """
    text = raw.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop opening fence line (```json or ```)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Slice from the first { to the last } to drop any surrounding prose
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text


async def decompose(
    prompt: str,
    raw_scores: dict[str, float],
    client: OpenRouterClient,
    settings: Settings,
    logger: structlog.BoundLogger | None = None,
) -> RoutingEnvelope:
    """Ask Haiku to decompose a prompt into one or more agent subtasks."""
    log = logger or structlog.get_logger(__name__)

    agent_configs = settings.agent_configs
    enabled = {
        name: cfg
        for name, cfg in agent_configs.items()
        if cfg.get("enabled", True)
    }
    known_agents = set(enabled)

    agent_descriptions = "\n".join(
        f"- {name}: {cfg['description'].strip()}"
        for name, cfg in enabled.items()
    )
    system = _SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)
    messages = [{"role": "user", "content": prompt}]

    fallback_model = settings.routing_config.get(
        "fallback_model", "anthropic/claude-haiku-4-5"
    )

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            raw = await client.complete(
                messages=messages,
                model=fallback_model,
                system=system,
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"},
                reasoning={"enabled": False},
            )
            data = json.loads(_extract_json_object(raw))
            subtasks = [
                SubTask(
                    agent=st["agent"],
                    intent=st["intent"],
                    prompt=st["prompt"],
                )
                for st in data["subtasks"]
            ]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            last_exc = RoutingError(f"Haiku returned invalid JSON (attempt {attempt + 1}): {exc}")
            log.warning("haiku_fallback_parse_error", attempt=attempt + 1, error=str(exc))
            continue

        unknown = [st.agent for st in subtasks if st.agent not in known_agents]
        if unknown:
            raise RoutingError(f"Haiku returned unknown agent(s): {unknown}")

        if not subtasks:
            log.warning("haiku_fallback_zero_subtasks", attempt=attempt + 1)
            last_exc = RoutingError("Haiku returned zero subtasks")
            continue

        is_compound = len(subtasks) > 1
        is_sequential = bool(data.get("sequential", False)) and is_compound
        primary = subtasks[0].agent

        return RoutingEnvelope(
            primary_agent=primary,
            confidence=raw_scores.get(primary, 0.0),
            score_gap=0.0,
            routing_method="haiku",
            is_compound=is_compound,
            subtasks=subtasks,
            requires_synthesis=is_compound and not is_sequential,
            raw_scores=raw_scores,
            is_sequential=is_sequential,
        )

    # Both attempts failed — fall back to companion rather than surfacing a routing
    # error to the user. Log the original failure so it's still observable.
    log.error(
        "haiku_fallback_exhausted",
        error=str(last_exc),
        fallback_agent="companion",
    )
    fallback = SubTask(agent="companion", intent="reason", prompt=prompt)
    return RoutingEnvelope(
        primary_agent="companion",
        confidence=0.0,
        score_gap=0.0,
        routing_method="haiku_fallback",
        is_compound=False,
        subtasks=[fallback],
        requires_synthesis=False,
        raw_scores=raw_scores,
        is_sequential=False,
    )
