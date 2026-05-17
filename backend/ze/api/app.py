import signal
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ze.api.openapi import OPENAPI_TAGS
from ze.api.routes import capabilities, memory, routing
from ze.capability.gate import CapabilityGate
from ze.db import create_pool
from ze.embeddings import get_embedder
from ze.logging import configure_logging, get_logger
from ze.memory.store import MemoryStore
from ze.openrouter.client import OpenRouterClient
from ze.orchestration.graph import build_graph
from ze.routing.router import EmbeddingRouter
from ze.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    pool = await create_pool(settings)
    http_client = httpx.AsyncClient(http2=True)
    embedder = get_embedder()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    openrouter_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        http_client=http_client,
        logger=get_logger("ze.openrouter"),
        http_referer=settings.openrouter_http_referer,
        title=settings.openrouter_title,
    )

    router = EmbeddingRouter(
        embedder=embedder,
        openrouter_client=openrouter_client,
        db_pool=pool,
        settings=settings,
    )

    capability_gate = CapabilityGate(config_path=settings.capabilities_path)
    memory_store = MemoryStore(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )
    graph = build_graph(checkpointer=checkpointer)

    app.state.pool = pool
    app.state.http_client = http_client
    app.state.embedder = embedder
    app.state.graph = graph
    app.state.openrouter_client = openrouter_client
    app.state.router = router
    app.state.capability_gate = capability_gate
    app.state.memory_store = memory_store

    signal.signal(signal.SIGHUP, lambda *_: capability_gate.reload())

    log.info("ze_startup_complete")
    yield

    log.info("ze_shutdown")
    await http_client.aclose()
    await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Ze API",
        version="0.1.0",
        description=(
            "Personal AI assistant API. REST endpoints manage capabilities, memory, "
            "and routing logs; real-time chat uses the WebSocket at `/ws/{session_id}`."
        ),
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(capabilities.router, prefix="/capabilities")
    app.include_router(memory.router, prefix="/memory")
    app.include_router(routing.router, prefix="/routing")

    from ze.api import ws
    app.add_api_websocket_route("/ws/{session_id}", ws.websocket_endpoint)

    return app


app = create_app()
