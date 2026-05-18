import json
import time

import structlog

from ze.agents.tool import ToolAccess, tool
from ze.agents.types import ToolCall
from ze.memory.types import UserFact
from ze.openrouter.client import OpenRouterClient

log = structlog.get_logger(__name__)

_SYSTEM = (
    "You extract facts about the user from AI assistant conversations. "
    "Only extract facts the user explicitly revealed about themselves "
    "(name, preferences, job, location, habits, goals, etc.). "
    "Return a JSON array — no markdown, no explanation, just the array. "
    'Each item: {"key": "snake_case_label", "value": "what was revealed", "confidence": 0.0-1.0}. '
    "If no user facts are present, return []."
)


@tool(access=ToolAccess.READ, description="Extract memorable user facts from a conversation turn.")
async def extract_facts(
    prompt: str,
    response: str,
    client: OpenRouterClient,
    model: str,
) -> ToolCall:
    args = {"prompt": prompt[:200], "response": response[:200]}
    start = time.monotonic()
    try:
        raw = await client.complete(
            messages=[{
                "role": "user",
                "content": f"User said: {prompt}\n\nAssistant replied: {response[:1000]}",
            }],
            model=model,
            system=_SYSTEM,
            max_tokens=300,
        )
        facts = _parse(raw)
        duration_ms = int((time.monotonic() - start) * 1000)
        return ToolCall(
            tool_name="extract_facts",
            args=args,
            result=facts,
            duration_ms=duration_ms,
            success=True,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning("extract_facts_failed", error=str(exc))
        return ToolCall(
            tool_name="extract_facts",
            args=args,
            result=[],
            duration_ms=duration_ms,
            success=False,
            error=str(exc),
        )


def _parse(raw: str) -> list[dict]:
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            return []
        return [
            {"key": str(f["key"]), "value": str(f["value"]), "confidence": float(f.get("confidence", 0.8))}
            for f in parsed
            if isinstance(f, dict) and "key" in f and "value" in f
        ]
    except (json.JSONDecodeError, KeyError, ValueError):
        return []


def to_user_facts(raw: list[dict], agent: str = "global") -> list[UserFact]:
    """Convert raw extract_facts result dicts into UserFact domain objects."""
    return [
        UserFact(
            key=f["key"],
            value=f["value"],
            agent=agent,
            confidence=float(f.get("confidence", 0.8)),
        )
        for f in raw
        if isinstance(f, dict) and f.get("key") and f.get("value")
    ]
