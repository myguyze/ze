from fastapi import Request
from sentence_transformers import SentenceTransformer

from ze.capability.gate import CapabilityGate
from ze.memory.store import MemoryStore
from ze.openrouter.client import OpenRouterClient
from ze.routing.router import EmbeddingRouter
from ze.settings import Settings, get_settings as _get_settings


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
