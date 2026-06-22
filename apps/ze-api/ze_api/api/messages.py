from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import MessageSchema
from ze_core.conversation.messages import MessageStore

router = APIRouter(tags=["messages"], dependencies=[Depends(require_api_key)])


def _get_message_store(request: Request) -> MessageStore:
    return request.app.state.message_store


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
    store: MessageStore = Depends(_get_message_store),
) -> list[MessageSchema]:
    if thread_id is not None:
        messages = await store.list_by_thread(thread_id, limit)
    elif since is not None:
        messages = await store.list_since(since, limit)
    else:
        since_default = datetime.fromisoformat("2000-01-01T00:00:00+00:00")
        messages = await store.list_since(since_default, limit)
    return [MessageSchema.model_validate(m.__dict__) for m in messages]
