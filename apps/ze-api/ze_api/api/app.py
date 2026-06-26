from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ze_api.api.openapi import OPENAPI_TAGS
from ze_api.api.routes import capabilities, channels, contacts, costs, data, dream, eval, goals, health, ingest, memory, news, reminders, routing, sessions, ui, version, webhooks, workflows, ws_schema
from ze_api.api.ws import router as ws_router
from ze_api.api.messages import router as messages_router
from ze_api.container import build_container
from ze_logging import configure_logging, get_logger
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
        openapi_components={
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "ApiKey",
                }
            }
        },
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_cors_origins(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Public — no auth required
    app.include_router(version.router)
    app.include_router(health.router, prefix="/api/v0")

    # WebSocket — auth handled by the WS handshake
    app.include_router(ws_router)

    # Internal tooling — exempt from versioning
    app.include_router(eval.router)

    # Versioned REST API
    app.include_router(capabilities.router, prefix="/api/v0/capabilities")
    app.include_router(memory.router, prefix="/api/v0/memory")
    app.include_router(routing.router, prefix="/api/v0/routing")
    app.include_router(workflows.router, prefix="/api/v0/workflows")
    app.include_router(costs.router, prefix="/api/v0/costs")
    app.include_router(goals.router, prefix="/api/v0")
    app.include_router(reminders.router, prefix="/api/v0")
    app.include_router(contacts.router, prefix="/api/v0")
    app.include_router(news.router, prefix="/api/v0")
    app.include_router(sessions.router, prefix="/api/v0")
    app.include_router(messages_router, prefix="/api/v0")
    app.include_router(data.router, prefix="/api/v0")
    app.include_router(ingest.router, prefix="/api/v0")
    app.include_router(ws_schema.router, prefix="/api/v0")
    app.include_router(dream.router, prefix="/api/v0")
    app.include_router(channels.router)
    app.include_router(ui.router)
    app.include_router(webhooks.router)

    return app


app = create_app()
