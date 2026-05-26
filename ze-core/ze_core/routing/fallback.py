from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from ze_core.errors import RoutingError
from ze_core.logging import get_logger
from ze_core.routing.types import LLMClient, RoutingEnvelope, SubTask

if TYPE_CHECKING:
    from ze_core.orchestration.base_agent import BaseAgent
    from ze_core.logging import _BoundLogger

_SYSTEM_PROMPT = """\
You are a routing assistant for a personal AI assistant.
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
- When uncertain and no tool use is needed, default to the first available agent with intent "reason".
- Use exactly one subtask for single-agent tasks.
- Use multiple subtasks only when the request genuinely requires different agents.
- Each subtask prompt must be self-contained for its agent.
- Set "sequential" to true when step N's output is needed as input for step N+1.
"""


def _extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text


def _hard_fallback_agent(
    agent_registry: dict[str, type[BaseAgent]],
    prompt: str,
    raw_scores: dict[str, float],
    log: _BoundLogger,
    last_exc: Exception | None,
) -> RoutingEnvelope:
    log.error("haiku_fallback_exhausted", error=str(last_exc))
    reason_agent = next(
        (name for name, cls in agent_registry.items() if "reason" in getattr(cls, "intent_map", {})),
        None,
    )
    fallback_name = reason_agent or next(iter(agent_registry))
    fallback = SubTask(agent=fallback_name, intent="reason", prompt=prompt)
    return RoutingEnvelope(
        primary_agent=fallback_name,
        confidence=0.0,
        score_gap=0.0,
        routing_method="haiku_fallback",
        is_compound=False,
        subtasks=[fallback],
        requires_synthesis=False,
        raw_scores=raw_scores,
        is_sequential=False,
    )


async def decompose(
    prompt: str,
    raw_scores: dict[str, float],
    client: LLMClient,
    agent_registry: dict[str, type[BaseAgent]],
    fallback_model: str,
    logger: _BoundLogger | None = None,
) -> RoutingEnvelope:
    log = logger or get_logger(__name__)
    known_agents = set(agent_registry)

    agent_descriptions = "\n".join(
        f"- {name}: {cls.description.strip()}"
        for name, cls in agent_registry.items()
    )
    system = _SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)
    messages = [{"role": "user", "content": prompt}]

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
            )
            data = json.loads(_extract_json_object(raw))
            raw_subtasks = data.get("subtasks", [])
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            last_exc = RoutingError(f"Haiku returned invalid JSON (attempt {attempt + 1}): {exc}")
            log.warning("haiku_fallback_parse_error", attempt=attempt + 1, error=str(exc))
            continue

        unknown = [st["agent"] for st in raw_subtasks if st.get("agent") not in known_agents]
        if unknown:
            raise RoutingError(f"Haiku returned unknown agent(s): {unknown}")

        if not raw_subtasks:
            log.warning("haiku_fallback_zero_subtasks", attempt=attempt + 1)
            last_exc = RoutingError("Haiku returned zero subtasks")
            continue

        subtasks = [
            SubTask(agent=st["agent"], intent=st["intent"], prompt=st["prompt"])
            for st in raw_subtasks
        ]
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

    return _hard_fallback_agent(agent_registry, prompt, raw_scores, log, last_exc)
