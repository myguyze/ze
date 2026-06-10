from fastapi import Request
from sentence_transformers import SentenceTransformer

from ze_core.capability.gate import CapabilityGate
from ze_memory.consolidator import MemoryConsolidator
from ze_memory.retriever import PostgresMemoryStore as MemoryStore
from ze_core.messages.store import PostgresMessageStore as MessageStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.routing.router import EmbeddingRouter
from ze_api.settings import Settings, get_settings as _get_settings


def get_settings() -> Settings:
    return _get_settings()


def get_pool(request: Request):
    return request.app.state.pool


def get_openrouter_client(request: Request) -> OpenRouterClient:
    return request.app.state.openrouter_client


def get_router(request: Request) -> EmbeddingRouter:
    return request.app.state.router


def get_capability_gate(request: Request) -> CapabilityGate:
    return request.app.state.capability_gate


def get_memory_store(request: Request) -> MemoryStore:
    return request.app.state.memory_store


def get_embedder(request: Request) -> SentenceTransformer:
    return request.app.state.embedder


def get_graph(request: Request):
    return request.app.state.graph


def get_workflow_store(request: Request):
    return request.app.state.workflow_store


def get_memory_consolidator(request: Request) -> MemoryConsolidator:
    return request.app.state.memory_consolidator


def get_message_store(request: Request) -> MessageStore:
    return request.app.state.message_store


def get_connection_manager(request: Request):
    return request.app.state.connection_manager
