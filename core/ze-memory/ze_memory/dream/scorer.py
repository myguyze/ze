from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ze_logging import get_logger
from ze_memory.consolidation_store import _cosine_similarity

log = get_logger(__name__)

_SIGNAL_ORIGIN_AGENTS = frozenset({"email", "calendar", "workflow", "reminders", "news"})
_TOOL_RESULT_MARKERS = ("tool_result", "tool_use", '"type": "tool"', "ToolResult", "<tool_response>")


def _classify_source(agent: str, prompt: str, response: str) -> str:
    agent_lower = agent.lower()
    if any(name in agent_lower for name in _SIGNAL_ORIGIN_AGENTS):
        return "ze_observed"
    combined = (prompt + " " + response).lower()
    if any(marker.lower() in combined for marker in _TOOL_RESULT_MARKERS):
        return "ze_observed"
    return "user_asserted"


def _novelty_score(episode_embedding: Any, existing_fact_embeddings: list[Any]) -> float:
    if not existing_fact_embeddings or episode_embedding is None:
        return 1.0
    max_sim = max(
        _cosine_similarity(episode_embedding, emb)
        for emb in existing_fact_embeddings
        if emb is not None
    )
    return max(0.0, 1.0 - max_sim)


def replay_score(
    episode: Any,
    now: datetime,
    existing_facts: list[Any],
    max_age_days: float = 30.0,
) -> float:
    if getattr(episode, "has_sensitive_entity", False):
        return 0.0

    created_at = getattr(episode, "created_at", None)
    if created_at is None:
        age_days = 0.0
    else:
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        age_days = (now - created_at).total_seconds() / 86400

    recency = max(0.0, 1.0 - age_days / max_age_days)
    relevance = getattr(episode, "relevance", 0.0) or 0.0
    confidence_inverse = 1.0 - relevance
    replay_count = getattr(episode, "replay_count", 0) or 0
    access_inverse = 1.0 / (1.0 + replay_count)

    episode_embedding = getattr(episode, "embedding", None)
    fact_embeddings = [getattr(f, "embedding", None) for f in existing_facts]
    novelty = _novelty_score(episode_embedding, [e for e in fact_embeddings if e is not None])

    source = getattr(episode, "source", "ze_observed")
    source_weight = 0.5 if source == "user_asserted" else 1.0

    return source_weight * (
        0.35 * recency
        + 0.25 * confidence_inverse
        + 0.25 * novelty
        + 0.15 * access_inverse
    )


async def tag_episode_metadata(
    pool: Any,
    episode_id: UUID,
    agent: str,
    prompt: str,
    response: str,
    relevance: float = 0.0,
) -> None:
    source = _classify_source(agent, prompt, response)
    # Simplified score at write time: novelty=1.0, recency=1.0, replay_count=0
    source_weight = 0.5 if source == "user_asserted" else 1.0
    initial_score = source_weight * (0.35 + 0.25 * (1.0 - relevance) + 0.25 + 0.15)
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_episode_metadata
                    (episode_id, replay_score, source, provenance, updated_at)
                VALUES ($1, $2, $3, 'raw', now())
                ON CONFLICT (episode_id) DO NOTHING
                """,
                episode_id,
                initial_score,
                source,
            )
    except Exception as exc:
        log.warning("tag_episode_metadata_failed", episode_id=str(episode_id), error=str(exc))
