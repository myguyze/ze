from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import CreateSessionRequest, SessionSchema
from ze_core.conversation.sessions import SessionStore

router = APIRouter(tags=["sessions"], dependencies=[Depends(require_api_key)])


def _get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store


@router.get(
    "/sessions",
    response_model=list[SessionSchema],
    operation_id="listSessions",
    summary="List chat sessions",
    description="Returns all chat sessions ordered by most recently active.",
)
async def list_sessions(
    store: SessionStore = Depends(_get_session_store),
) -> list[SessionSchema]:
    sessions = await store.list_all()
    return [SessionSchema.model_validate(s.__dict__) for s in sessions]


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
    return SessionSchema.model_validate(session.__dict__)
