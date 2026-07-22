from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ze_core.capability.gate import CapabilityGate
from ze_memory.consolidator import MemoryConsolidator
from ze_memory.retriever import PostgresMemoryStore as MemoryStore
from ze_core.conversation.messages import PostgresMessageStore as MessageStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.routing.router import EmbeddingRouter
from ze_api.settings import Settings, get_settings as _get_settings


_bearer = HTTPBearer(auto_error=False)


async def require_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    expected: str = request.app.state.settings.ze_api_key
    token = credentials.credentials if credentials else ""
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key"
        )


def get_settings() -> Settings:
    return _get_settings()


def get_container(request: Request):
    return request.app.state.container


def get_pool(request: Request):
    return request.app.state.container.pool


def get_openrouter_client(request: Request) -> OpenRouterClient:
    return request.app.state.container.openrouter_client


def get_router(request: Request) -> EmbeddingRouter:
    return request.app.state.container.router


def get_capability_gate(request: Request) -> CapabilityGate:
    return request.app.state.container.capability_gate


def get_memory_store(request: Request) -> MemoryStore:
    return request.app.state.container.memory_store


def get_embedder(request: Request):
    return request.app.state.container.embedder


def get_graph(request: Request):
    return request.app.state.container.graph


def get_workflow_store(request: Request):
    return request.app.state.container.workflow_store


def get_memory_consolidator(request: Request) -> MemoryConsolidator:
    return request.app.state.container.memory_consolidator


def get_message_store(request: Request) -> MessageStore:
    return request.app.state.container.message_store


def get_connection_manager(request: Request):
    return request.app.state.container.connection_manager


def get_dream_store(request: Request):
    return request.app.state.container.dream_store


def get_notification_store(request: Request):
    return request.app.state.container.notification_store


def get_loop_store(request: Request):
    return request.app.state.container.loop_store
