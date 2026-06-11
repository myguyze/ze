from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request

from ze_api.api.schemas import MessageSchema
from ze_core.messages.store import MessageStore

router = APIRouter(tags=["messages"])


def _get_message_store(request: Request) -> MessageStore:
    return request.app.state.message_store


@router.get(
    "/api/messages",
    response_model=list[MessageSchema],
    summary="Load message history",
    description="Returns messages after `since` (ISO 8601), newest-last. Max 200.",
)
async def list_messages(
    since: datetime = Query(..., description="Load messages after this timestamp (ISO 8601)"),
    limit: int = Query(default=100, le=200),
    store: MessageStore = Depends(_get_message_store),
) -> list[MessageSchema]:
    messages = await store.list_since(since, limit)
    return [MessageSchema.model_validate(m.__dict__) for m in messages]
