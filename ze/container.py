from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from ze.agents.bootstrap import bootstrap_agents
from ze.capability.gate import CapabilityGate
from ze.db import create_checkpointer_pool, create_pool, dispose_checkpointer_pool
from ze.embeddings import get_embedder
from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.openrouter.client import OpenRouterClient
from ze.orchestration.graph import build_graph
from ze.orchestration.workflow_graph import build_workflow_graph
from ze.routing.router import EmbeddingRouter
from ze.settings import Settings
from ze.telegram.bot import ZeBot
from ze.telegram.session import ActiveSessionStore
from ze.workflow.planner import WorkflowPlanner
from ze.workflow.scheduler import WorkflowScheduler
from ze.workflow.store import WorkflowStore

log = get_logger(__name__)


@dataclass
class Container:
    """Holds all shared resources for the Ze application lifetime."""

    settings: Settings
    pool: object
    checkpointer_pool: object
    embedder: object
    openrouter_client: OpenRouterClient
    router: EmbeddingRouter
    capability_gate: CapabilityGate
    memory_store: MemoryStore
    workflow_store: WorkflowStore
    workflow_scheduler: WorkflowScheduler
    graph: object
    bot: Bot
    ze_bot: ZeBot

    async def close(self) -> None:
        await self.workflow_scheduler.stop()
        await self.bot.session.close()
        await self.openrouter_client.aclose()
        await dispose_checkpointer_pool(self.checkpointer_pool)
        await self.pool.close()
        log.info("container_closed")


async def build_container(settings: Settings) -> Container:
    pool = await create_pool(settings)
    checkpointer_pool = await create_checkpointer_pool(settings)
    embedder = get_embedder()

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("ze.routing.types", "SubTask"),
            ("ze.routing.types", "RoutingEnvelope"),
            ("ze.agents.types", "ToolCall"),
            ("ze.agents.types", "AgentResult"),
            ("ze.agents.types", "AgentContext"),
            ("ze.capability.types", "GateDecision"),
            ("ze.memory.types", "MemoryContext"),
            ("ze.memory.types", "UserFact"),
            ("asyncpg.pgproto.pgproto", "UUID"),
        ]
    )
    checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=serde)
    await checkpointer.setup()

    openrouter_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
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

    # ── Workflow ──────────────────────────────────────────────────────────────
    workflow_store = WorkflowStore(db_pool=pool)
    workflow_planner = WorkflowPlanner(openrouter_client=openrouter_client, settings=settings)
    workflow_graph = build_workflow_graph(checkpointer=checkpointer)

    # The graph_config mirrors _make_config in ZeBot — passed to the scheduler
    # so scheduled workflow runs have access to all required services.
    workflow_graph_config = {
        "configurable": {
            "router": router,
            "capability_gate": capability_gate,
            "memory_store": memory_store,
            "openrouter_client": openrouter_client,
            "embedder": embedder,
            "settings": settings,
        }
    }

    workflow_scheduler = WorkflowScheduler(
        workflow_store=workflow_store,
        workflow_graph=workflow_graph,
        graph_config=workflow_graph_config,
        settings=settings,
    )

    bootstrap_agents(
        openrouter_client=openrouter_client,
        settings=settings,
        workflow_store=workflow_store,
        workflow_planner=workflow_planner,
        workflow_scheduler=workflow_scheduler,
    )
    graph = build_graph(checkpointer=checkpointer)

    await workflow_scheduler.start()

    bot = Bot(token=settings.telegram_bot_token)
    if settings.telegram_bot_token and settings.public_url:
        await bot.set_webhook(
            url=f"{settings.public_url}/telegram/webhook",
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        log.info("telegram_webhook_registered", url=settings.public_url)

    ze_bot = ZeBot(
        bot=bot,
        graph=graph,
        store=ActiveSessionStore(),
        router=router,
        capability_gate=capability_gate,
        memory_store=memory_store,
        openrouter_client=openrouter_client,
        embedder=embedder,
        settings=settings,
    )

    return Container(
        settings=settings,
        pool=pool,
        checkpointer_pool=checkpointer_pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        router=router,
        capability_gate=capability_gate,
        memory_store=memory_store,
        workflow_store=workflow_store,
        workflow_scheduler=workflow_scheduler,
        graph=graph,
        bot=bot,
        ze_bot=ze_bot,
    )
