from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import (
    CreateSessionRequest,
    SessionListResponse,
    SessionSchema,
    SessionSearchResult,
)
from ze_core.conversation.sessions import SessionSearchHit, SessionStore

router = APIRouter(tags=["sessions"], dependencies=[Depends(require_api_key)])


def _get_session_store(request: Request) -> SessionStore:
    return request.app.state.container.session_store


def _session_to_schema(session) -> SessionSchema:
    return SessionSchema.model_validate(session.__dict__)


def _search_hit_to_result(hit: SessionSearchHit) -> SessionSearchResult:
    data = {
        **hit.session.__dict__,
        "match_source": hit.match_source,
        "snippet": hit.snippet,
        "rank": hit.rank,
    }
    return SessionSearchResult.model_validate(data)


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    operation_id="listSessions",
    summary="List chat sessions",
    description="Returns chat sessions ordered by most recently active, cursor-paginated via `before`.",
)
async def list_sessions(
    limit: int = Query(default=30, ge=1, le=100, description="Max sessions per page"),
    before: datetime | None = Query(
        default=None,
        description="Return sessions with last_active_at strictly older than this timestamp",
    ),
    store: SessionStore = Depends(_get_session_store),
) -> SessionListResponse:
    page = await store.list_page(limit=limit, before=before)
    return SessionListResponse(
        items=[_session_to_schema(s) for s in page.items],
        next_before=page.next_before,
    )


@router.get(
    "/sessions/search",
    response_model=list[SessionSearchResult],
    operation_id="searchSessions",
    summary="Search chat sessions",
    description="Full-text search across message content, session metadata, and archived session summaries.",
)
async def search_sessions(
    q: str = Query(
        min_length=1, description="Search query (min 2 characters for results)"
    ),
    limit: int = Query(default=20, ge=1, le=50, description="Max results"),
    store: SessionStore = Depends(_get_session_store),
) -> list[SessionSearchResult]:
    hits = await store.search(q, limit=limit)
    return [_search_hit_to_result(hit) for hit in hits]


@router.post(
    "/sessions",
    response_model=SessionSchema,
    operation_id="createSession",
    summary="Create a chat session",
    description="Creates a new session and returns it. A UUID is minted server-side when id is omitted.",
    status_code=201,
)
async def create_session(
    body: CreateSessionRequest,
    store: SessionStore = Depends(_get_session_store),
) -> SessionSchema:
    session_id = body.id or str(uuid4())
    session = await store.create(session_id, title=body.title)
    return _session_to_schema(session)
