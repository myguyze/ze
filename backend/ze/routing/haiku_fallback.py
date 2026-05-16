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
  ]
}}

Intent values: read, create, update, delete, execute, reason
- Use exactly one subtask for single-agent tasks.
- Use multiple subtasks only when the request genuinely requires different agents.
- Each subtask prompt must be self-contained for its agent.
"""


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
            )
            data = json.loads(raw)
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
            last_exc = RoutingError("Haiku returned zero subtasks")
            continue

        is_compound = len(subtasks) > 1
        primary = subtasks[0].agent

        return RoutingEnvelope(
            primary_agent=primary,
            confidence=raw_scores.get(primary, 0.0),
            score_gap=0.0,
            routing_method="haiku",
            is_compound=is_compound,
            subtasks=subtasks,
            requires_synthesis=is_compound,
            raw_scores=raw_scores,
        )

    raise last_exc or RoutingError("Haiku decomposition failed after 2 attempts")
