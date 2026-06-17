from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ze_api.api.openapi import OPENAPI_TAGS
from ze_api.api.routes import capabilities, contacts, costs, eval, goals, health, memory, news, reminders, routing, sessions, workflows
from ze_api.data.routes import router as data_router
from ze_api.api.ws import router as ws_router
from ze_api.api.messages import router as messages_router
from ze_api.container import build_container
from ze_api.logging import configure_logging, get_logger
from ze_api import migrate as ze_migrate
from ze_api.settings import get_settings

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(
        settings.log_level,
        dev=settings.log_dev,
        log_file=settings.log_file,
    )

    if settings.auto_migrate:
        log.info("ze_auto_migrate_start")
        ze_migrate.upgrade(settings.database_url_sync)
        log.info("ze_auto_migrate_done")

    ze_migrate.assert_schema_ready(settings.database_url_sync)

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
    app.state.session_store = container.session_store
    app.state.connection_manager = container.connection_manager
    app.state.confirmation_store = container.confirmation_store
    app.state.onboarding_coordinator = container.onboarding_coordinator
    app.state.reset_service = container.reset_service
    app.state.data_portability_service = container.data_portability_service
    app.state.container = container

    log.info("ze_startup_complete")
    yield

    log.info("ze_shutdown")
    await container.close()


def _parse_cors_origins(value: str) -> list[str]:
    if value.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def create_app() -> FastAPI:
    settings = get_settings()
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_cors_origins(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(capabilities.router, prefix="/capabilities")
    app.include_router(memory.router, prefix="/memory")
    app.include_router(routing.router, prefix="/routing")
    app.include_router(workflows.router, prefix="/workflows")
    app.include_router(costs.router, prefix="/costs")
    app.include_router(costs.web_router)
    app.include_router(goals.router)
    app.include_router(reminders.router)
    app.include_router(contacts.router)
    app.include_router(news.router)
    app.include_router(sessions.router)
    app.include_router(health.router)
    app.include_router(ws_router)
    app.include_router(messages_router)
    app.include_router(eval.router)
    app.include_router(data_router)

    return app


app = create_app()
