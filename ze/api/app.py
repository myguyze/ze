import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ze.api.openapi import OPENAPI_TAGS
from ze.api.routes import capabilities, memory, routing, workflows
from ze.api.telegram import router as telegram_router
from ze.container import build_container
from ze.logging import configure_logging, get_logger
from ze.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    container = await build_container(settings)

    app.state.settings = settings
    app.state.pool = container.pool
    app.state.embedder = container.embedder
    app.state.graph = container.graph
    app.state.openrouter_client = container.openrouter_client
    app.state.router = container.router
    app.state.capability_gate = container.capability_gate
    app.state.memory_store = container.memory_store
    app.state.ze_bot = container.ze_bot
    app.state.workflow_store = container.workflow_store

    signal.signal(signal.SIGHUP, lambda *_: container.capability_gate.reload())

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
            "and routing logs. Chat is handled by the Telegram bot."
        ),
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )

    app.include_router(capabilities.router, prefix="/capabilities")
    app.include_router(memory.router, prefix="/memory")
    app.include_router(routing.router, prefix="/routing")
    app.include_router(workflows.router, prefix="/workflows")
    app.include_router(telegram_router)

    return app


app = create_app()
