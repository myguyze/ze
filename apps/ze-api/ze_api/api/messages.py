from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ze_api.api.dependencies import get_message_store, require_api_key
from ze_api.api.schemas import MessageSchema, MessageTraceResponse
from ze_core.conversation.messages import MessageStore

router = APIRouter(tags=["messages"], dependencies=[Depends(require_api_key)])


@router.get(
    "/messages",
    response_model=list[MessageSchema],
    operation_id="listMessages",
    summary="Load message history",
    description=(
        "Returns messages after `since` (ISO 8601), oldest-first. Max 200. "
        "Pass `thread_id` to load messages for a specific session."
    ),
)
async def list_messages(
    since: datetime | None = Query(default=None, description="Load messages after this timestamp (ISO 8601)"),
    thread_id: str | None = Query(default=None, description="Filter by session thread ID"),
    limit: int = Query(default=100, le=200),
    store: MessageStore = Depends(get_message_store),
) -> list[MessageSchema]:
    if thread_id is not None:
        messages = await store.list_by_thread(thread_id, limit)
    elif since is not None:
        messages = await store.list_since(since, limit)
    else:
        since_default = datetime.fromisoformat("2000-01-01T00:00:00+00:00")
        messages = await store.list_since(since_default, limit)
    return [MessageSchema.model_validate(m.__dict__) for m in messages]


@router.get(
    "/messages/{message_id}/trace",
    response_model=MessageTraceResponse,
    operation_id="getMessageTrace",
    summary="Get message trace",
    description=(
        "Returns the execution trace for an AI message — routing decision, "
        "memory chunks retrieved, and tool calls made. 404 for user messages "
        "or messages without a trace (pre-Phase-89)."
    ),
)
async def get_message_trace(
    message_id: UUID,
    store: MessageStore = Depends(get_message_store),
) -> MessageTraceResponse:
    trace = await store.get_trace(message_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return MessageTraceResponse(
        agent=trace.agent,
        routing_method=trace.routing_method,
        confidence=trace.confidence,
        score_gap=trace.score_gap,
        is_compound=trace.is_compound,
        subtasks=trace.subtasks,
        memory_chunks=[
            {"text": c.text, "score": c.score, "source": c.source}
            for c in trace.memory_chunks
        ],
        tool_calls=[
            {
                "name": t.name,
                "result_snippet": t.result_snippet,
                "duration_ms": t.duration_ms,
                "success": t.success,
            }
            for t in trace.tool_calls
        ],
        total_duration_ms=trace.total_duration_ms,
    )
