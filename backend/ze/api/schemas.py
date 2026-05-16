from typing import Annotated, Literal
from uuid import UUID as UUIDType

from pydantic import BaseModel, Field


# ── WebSocket: client → server ────────────────────────────────────────────────

class UserMessage(BaseModel):
    type: Literal["message"]
    content: str


class ConfirmMessage(BaseModel):
    type: Literal["confirm"]
    decision: Literal["yes", "no", "edit"]
    edit_content: str | None = None


WsClientMessage = Annotated[
    UserMessage | ConfirmMessage,
    Field(discriminator="type"),
]


# ── WebSocket: server → client ────────────────────────────────────────────────

class TokenMessage(BaseModel):
    type: Literal["token"] = "token"
    content: str


class ConfirmationRequest(BaseModel):
    type: Literal["confirmation_request"] = "confirmation_request"
    draft: str
    agent: str
    action: str


class DoneMessage(BaseModel):
    type: Literal["done"] = "done"
    agent: str
    routing_method: str
    confidence: float | None


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class ConfirmationExpiredMessage(BaseModel):
    type: Literal["confirmation_expired"] = "confirmation_expired"


WsServerMessage = (
    TokenMessage
    | ConfirmationRequest
    | DoneMessage
    | ErrorMessage
    | ConfirmationExpiredMessage
)


# ── REST: capabilities ────────────────────────────────────────────────────────

class CapabilityModeUpdate(BaseModel):
    mode: Literal["autonomous", "confirm", "draft_only", "disabled"]


# ── REST: memory ──────────────────────────────────────────────────────────────

class FactReviewAction(BaseModel):
    id: UUIDType
    action: Literal["confirm", "reject", "edit"]
    value: str | None = None


class FactReviewRequest(BaseModel):
    actions: list[FactReviewAction]


# ── REST: routing log ─────────────────────────────────────────────────────────

class RoutingLogEntry(BaseModel):
    id: UUIDType
    session_id: str
    prompt: str
    method: str
    primary_agent: str
    confidence: float | None
    score_gap: float | None
    is_compound: bool
    raw_scores: dict[str, float] | None
    created_at: str
