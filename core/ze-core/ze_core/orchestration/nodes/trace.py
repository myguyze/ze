from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from ze_core.conversation.messages.types import (
    MemoryChunkTrace,
    MessageTrace,
    ToolCallTrace,
)
from ze_core.orchestration.state import AgentState


_MAX_MEMORY_CHUNKS = 10


async def record_trace(state: AgentState, config: RunnableConfig) -> dict:
    envelope = state.get("envelope")
    agent_result = state.get("agent_result")

    if envelope is None:
        return {}

    memory_chunks = _extract_memory_chunks(state.get("memory_context"))
    tool_calls = _extract_tool_calls(agent_result)
    total_duration_ms = sum(t.duration_ms for t in tool_calls)

    subtask_agents = (
        [envelope.primary_agent]
        if not envelope.is_compound
        else [s.agent for s in envelope.subtasks]
    )

    trace = MessageTrace(
        agent=envelope.primary_agent,
        routing_method=envelope.routing_method,
        confidence=envelope.confidence,
        score_gap=envelope.score_gap,
        is_compound=envelope.is_compound,
        subtasks=subtask_agents,
        memory_chunks=memory_chunks,
        tool_calls=tool_calls,
        total_duration_ms=total_duration_ms,
    )
    return {"message_trace": trace}


def _extract_memory_chunks(memory_context: Any) -> list[MemoryChunkTrace]:
    if memory_context is None:
        return []

    chunks: list[MemoryChunkTrace] = []

    facts = getattr(memory_context, "facts", []) or []
    for fact in facts[:5]:
        text = f"{fact.predicate}: {fact.value}"
        chunks.append(
            MemoryChunkTrace(
                text=text[:300],
                score=getattr(fact, "relevance_score", None) or 0.0,
                source="fact",
                extraction_confidence=getattr(fact, "confidence", None),
            )
        )

    episodes = getattr(memory_context, "episodes", []) or []
    for ep in episodes[:5]:
        text = getattr(ep, "summary", None) or (
            ep.response[:300] if hasattr(ep, "response") else ""
        )
        chunks.append(
            MemoryChunkTrace(
                text=text[:300],
                score=getattr(ep, "relevance_score", None) or 0.0,
                source="episode",
            )
        )

    return chunks[:_MAX_MEMORY_CHUNKS]


def _extract_tool_calls(agent_result: Any) -> list[ToolCallTrace]:
    if agent_result is None:
        return []
    raw_calls = getattr(agent_result, "tool_calls", []) or []
    result = []
    for tc in raw_calls:
        raw_result = getattr(tc, "result", "") or ""
        snippet = str(raw_result)[:200] if raw_result else ""
        result.append(
            ToolCallTrace(
                name=getattr(tc, "tool_name", "unknown"),
                result_snippet=snippet,
                duration_ms=getattr(tc, "duration_ms", 0),
                success=getattr(tc, "success", True),
            )
        )
    return result
