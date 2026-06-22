"""LLM-based extraction of user facts and events from a completed conversation turn."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from typing import TYPE_CHECKING

from ze_logging import get_logger

from ze_memory.defaults import MODEL_SYNTHESIS
from ze_memory.types import Event, Fact

if TYPE_CHECKING:
    from ze_memory.types import Entity

log = get_logger(__name__)

_SYSTEM = (
    "You extract facts about the user from AI assistant conversations. "
    "Only extract facts the user explicitly revealed about themselves "
    "(name, preferences, job, location, habits, goals, etc.). "
    "Return a JSON array — no markdown, no explanation, just the array. "
    'Each item: {"predicate": "snake_case_label", "value": "what was revealed", "confidence": 0.0-1.0}. '
    "If no user facts are present, return []."
)


def fact_extraction_model(settings: Any = None) -> str:
    if settings is None:
        return MODEL_SYNTHESIS
    if isinstance(settings, dict):
        memory = settings.get("memory", {})
        override = memory.get("fact_extraction_model") if isinstance(memory, dict) else None
        if override:
            return override
        return settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
    cfg = getattr(settings, "config", None)
    if isinstance(cfg, dict):
        memory = cfg.get("memory", {})
        override = memory.get("fact_extraction_model") if isinstance(memory, dict) else None
        if override:
            return override
        return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
    return MODEL_SYNTHESIS


def parse_fact_response(raw: str) -> list[dict]:
    text = raw.strip()
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
            {
                "predicate": str(f.get("predicate") or f.get("key", "")),
                "value": str(f["value"]),
                "confidence": float(f.get("confidence", 0.8)),
            }
            for f in parsed
            if isinstance(f, dict) and f.get("value")
            and (f.get("predicate") or f.get("key"))
        ]
    except (json.JSONDecodeError, KeyError, ValueError):
        return []


def raw_to_facts(raw: list[dict]) -> list[Fact]:
    return [
        Fact(
            id=None,
            subject_id=None,
            predicate=f["predicate"],
            object_text=None,
            object_id=None,
            value=f["value"],
            confidence=float(f.get("confidence", 0.8)),
        )
        for f in raw
        if isinstance(f, dict) and f.get("predicate") and f.get("value")
    ]


def merge_fact_proposals(explicit: list[Fact], extracted: list[Fact]) -> list[Fact]:
    """Agent-supplied proposals override extracted facts with the same predicate."""
    by_predicate = {f.predicate: f for f in extracted}
    for fact in explicit:
        by_predicate[fact.predicate] = fact
    return list(by_predicate.values())


async def extract_facts(
    client: Any,
    *,
    prompt: str,
    response: str,
    model: str,
) -> list[Fact]:
    if response.startswith("[ERROR]"):
        return []
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
        return raw_to_facts(parse_fact_response(raw))
    except Exception as exc:
        log.warning("memory_fact_extraction_failed", error=str(exc))
        return []


def _coerce_fact(item: Any) -> Fact | None:
    if isinstance(item, Fact):
        return item
    if isinstance(item, dict) and item.get("value"):
        predicate = item.get("predicate") or item.get("key")
        if not predicate:
            return None
        return Fact(
            id=None,
            subject_id=None,
            predicate=str(predicate),
            object_text=None,
            object_id=None,
            value=str(item["value"]),
            confidence=float(item.get("confidence", 0.8)),
        )
    return None


_EVENT_SYSTEM = (
    "You extract events from AI assistant conversations. "
    "An event is anything that happened (or will happen) at a point in time that is worth remembering: "
    "meetings, calls, trips, appointments, meals, decisions made, accomplishments achieved, "
    "milestones reached, experiences had, or any other significant occurrence. "
    "Only extract events the user explicitly mentioned — do not infer. "
    "Return a JSON array — no markdown, just the array. "
    'Each item: {"event_type": "meeting|call|trip|appointment|meal|decision|accomplishment|experience|milestone|other", '
    '"title": "concise description", '
    '"start_at": "ISO8601 datetime or null", "end_at": "ISO8601 datetime or null", '
    '"participants": ["name1", "name2"], '
    '"outcome": "result/outcome if already past, or null"}. '
    "If no events are present, return []."
)


def parse_event_response(raw: str) -> list[dict]:
    text = raw.strip()
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
            e for e in parsed
            if isinstance(e, dict) and e.get("title") and e.get("event_type")
        ]
    except (json.JSONDecodeError, ValueError):
        return []


def _parse_dt(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def raw_to_events(raw: list[dict]) -> list[Event]:
    return [
        Event(
            id=None,
            event_type=e.get("event_type", "other"),
            title=e["title"],
            start_at=_parse_dt(e.get("start_at")),
            end_at=_parse_dt(e.get("end_at")),
            participant_names=[str(p) for p in e.get("participants", []) if p],
            outcome=e.get("outcome") or None,
        )
        for e in raw
        if isinstance(e, dict) and e.get("title") and e.get("event_type")
    ]


async def extract_events(
    client: Any,
    *,
    prompt: str,
    response: str,
    model: str,
) -> list[Event]:
    if response.startswith("[ERROR]"):
        return []
    try:
        raw = await client.complete(
            messages=[{
                "role": "user",
                "content": f"User said: {prompt}\n\nAssistant replied: {response[:1000]}",
            }],
            model=model,
            system=_EVENT_SYSTEM,
            max_tokens=400,
        )
        return raw_to_events(parse_event_response(raw))
    except Exception as exc:
        log.warning("memory_event_extraction_failed", error=str(exc))
        return []


async def gather_event_proposals(
    configurable: dict,
    *,
    prompt: str,
    response: str,
) -> list[Event]:
    """Extract conversational events (past or future) from a conversation turn."""
    client = configurable.get("openrouter_client")
    if client is None:
        return []

    settings = configurable.get("settings")
    settings_dict = (
        settings.config if settings is not None and hasattr(settings, "config") else settings
    )
    model = fact_extraction_model(settings_dict)
    return await extract_events(client, prompt=prompt, response=response, model=model)


_ENTITY_SYSTEM = (
    "You extract named entities from AI assistant conversations. "
    "Only extract proper nouns explicitly mentioned: people, organisations, places, products, projects, or concepts. "
    "Do not extract generic terms, pronouns, or inferred entities. "
    "Return a JSON array — no markdown, just the array. "
    'Each item: {"name": "canonical name", "entity_type": "person|organisation|place|product|project|concept", '
    '"aliases": ["alt name 1"]}. '
    "If no named entities are present, return []."
)


def raw_to_entities(raw: list[dict]) -> list["Entity"]:
    from ze_memory.types import Entity
    return [
        Entity(
            id=None,
            entity_type=e.get("entity_type", "concept"),
            canonical_name=str(e["name"]),
            aliases=[str(a) for a in e.get("aliases", []) if a],
            attrs={},
        )
        for e in raw
        if isinstance(e, dict) and e.get("name") and e.get("entity_type")
    ]


async def extract_entities(
    client: Any,
    *,
    prompt: str,
    response: str,
    model: str,
) -> list["Entity"]:
    if response.startswith("[ERROR]"):
        return []
    try:
        raw_text = await client.complete(
            messages=[{
                "role": "user",
                "content": f"User said: {prompt}\n\nAssistant replied: {response[:1000]}",
            }],
            model=model,
            system=_ENTITY_SYSTEM,
            max_tokens=300,
        )
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        try:
            import json as _json
            parsed = _json.loads(text)
            if not isinstance(parsed, list):
                return []
            return raw_to_entities([
                e for e in parsed
                if isinstance(e, dict) and e.get("name") and e.get("entity_type")
            ])
        except (_json.JSONDecodeError, ValueError):
            return []
    except Exception as exc:
        log.warning("memory_entity_extraction_failed", error=str(exc))
        return []


async def gather_entity_proposals(
    configurable: dict,
    *,
    prompt: str,
    response: str,
) -> list["Entity"]:
    """Extract named entities from a conversation turn."""
    client = configurable.get("openrouter_client")
    if client is None:
        return []

    settings = configurable.get("settings")
    settings_dict = (
        settings.config if settings is not None and hasattr(settings, "config") else settings
    )
    model = fact_extraction_model(settings_dict)
    return await extract_entities(client, prompt=prompt, response=response, model=model)


async def gather_fact_proposals(
    configurable: dict,
    *,
    agent: str,
    prompt: str,
    response: str,
    explicit: list,
) -> list[Fact]:
    """Merge agent-supplied proposals with LLM-extracted facts from the turn."""
    explicit_facts = [_coerce_fact(f) for f in explicit]
    explicit_facts = [f for f in explicit_facts if f is not None]

    client = configurable.get("openrouter_client")
    if client is None:
        return explicit_facts

    settings = configurable.get("settings")
    settings_dict = (
        settings.config if settings is not None and hasattr(settings, "config") else settings
    )
    model = fact_extraction_model(settings_dict)
    extracted = await extract_facts(
        client,
        prompt=prompt,
        response=response,
        model=model,
    )
    return merge_fact_proposals(explicit_facts, extracted)
