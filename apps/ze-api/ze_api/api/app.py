import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ze_api.api.openapi import OPENAPI_TAGS
from ze_api.api.routes import capabilities, costs, eval, memory, routing, workflows
from ze_api.api.ws import router as ws_router
from ze_api.api.messages import router as messages_router
from ze_api.container import build_container
from ze_api.logging import configure_logging, get_logger
from ze_api.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level, log_file=settings.log_file)

    container = await build_container(settings)

    app.state.settings = settings
    app.state.pool = container.pool
    app.state.embedder = container.embedder
    app.state.graph = container.graph
    app.state.openrouter_client = container.openrouter_client
    app.state.router = container.router
    app.state.capability_gate = container.capability_gate
    app.state.memory_store = container.memory_store
    app.state.memory_consolidator = container.memory_consolidator
    app.state.workflow_store = container.workflow_store
    app.state.message_store = container.message_store
    app.state.connection_manager = container.connection_manager
    app.state.confirmation_store = container.confirmation_store
    app.state.container = container

    log.info("ze_startup_complete")
    yield

    log.info("ze_shutdown")
    await container.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ze API",
        version="0.1.0",
        description=(
            "Personal AI assistant API. REST endpoints manage capabilities, memory, "
            "and routing logs. Chat is handled via WebSocket at /ws."
        ),
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )

    app.include_router(capabilities.router, prefix="/capabilities")
    app.include_router(memory.router, prefix="/memory")
    app.include_router(routing.router, prefix="/routing")
    app.include_router(workflows.router, prefix="/workflows")
    app.include_router(costs.router, prefix="/costs")
    app.include_router(ws_router)
    app.include_router(messages_router)
    app.include_router(eval.router)

    return app


app = create_app()
