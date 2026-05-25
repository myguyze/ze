from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram import Bot
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from ze.agents.bootstrap import bootstrap_agents
from ze.browser.client import BrowserClient
from ze.capability.gate import CapabilityGate
from ze.channels.email import EmailChannel
from ze.channels.registry import ChannelRegistry
from ze.contacts.channel_store import ContactChannelStore
from ze.db import create_checkpointer_pool, create_pool, dispose_checkpointer_pool
from ze.embeddings import get_embedder
from ze.goals.executor import GoalExecutor
from ze.goals.planner import GoalPlanner
from ze.goals.store import GoalStore
from ze.google.auth import GoogleCredentials
from ze.logging import get_logger
from ze.contacts.consolidator import ContactsConsolidator
from ze.contacts.store import PersonStore
from ze.proactive.contacts import ContactReviewNotifier
from ze.proactive.prospecting import recover_stale_campaigns
from ze.memory.consolidator import MemoryConsolidator
from ze.memory.store import MemoryStore
from ze.persona.store import PersonaStore
from ze.openrouter.client import OpenRouterClient
from ze.orchestration.graph import build_graph
from ze.progress.translations import ProgressTranslations
from ze.reminders.store import ReminderStore, fire_reminder
from ze.orchestration.workflow_graph import build_workflow_graph
from ze.proactive.briefing import MorningBriefing
from ze.proactive.insights import InsightEngine
from ze.proactive.notifier import ProactiveNotifier
from ze.proactive.reminders import CalendarReminderScheduler
from ze.routing.complexity import ComplexityEstimator
from ze.routing.router import EmbeddingRouter
from ze.settings import Settings
from ze.telegram.bot import ZeBot
from ze.telegram.session import ActiveSessionStore
from ze.telemetry.reconciler import CostReconciler
from ze.telemetry.tracker import CostTracker
from ze.transcription.client import TranscriptionClient
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
    person_store: PersonStore
    memory_consolidator: MemoryConsolidator
    contacts_consolidator: ContactsConsolidator
    workflow_store: WorkflowStore
    workflow_scheduler: WorkflowScheduler
    graph: object
    bot: Bot
    ze_bot: ZeBot
    notifier: ProactiveNotifier
    morning_briefing: MorningBriefing
    calendar_reminders: CalendarReminderScheduler
    insight_engine: InsightEngine
    browser_client: BrowserClient
    channel_registry: ChannelRegistry
    contact_channel_store: ContactChannelStore
    goal_store: GoalStore
    goal_executor: GoalExecutor

    async def close(self) -> None:
        await self.workflow_scheduler.stop()
        await self.bot.session.close()
        await self.openrouter_client.aclose()
        await self.browser_client.close()
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
            ("ze.memory.types", "Episode"),
            ("ze.memory.types", "UserProfile"),
            ("asyncpg.pgproto.pgproto", "UUID"),
        ]
    )
    checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=serde)
    await checkpointer.setup()

    cost_tracker = CostTracker(pool=pool)

    openrouter_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        logger=get_logger("ze.openrouter"),
        http_referer=settings.openrouter_http_referer,
        title=settings.openrouter_title,
        cost_tracker=cost_tracker,
    )

    estimator = ComplexityEstimator()
    router = EmbeddingRouter(
        embedder=embedder,
        openrouter_client=openrouter_client,
        db_pool=pool,
        settings=settings,
        estimator=estimator,
    )

    capability_gate = CapabilityGate(config_path=settings.capabilities_path)
    memory_store = MemoryStore(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    browser_client = BrowserClient(
        base_url=settings.browser_service_url,
        timeout=settings.browser_timeout_seconds,
    )

    persona_store = PersonaStore(pool=pool, settings=settings)
    person_store = PersonStore(pool=pool)
    contacts_consolidator = ContactsConsolidator(
        pool=pool,
        person_store=person_store,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    # ── Memory consolidation ──────────────────────────────────────────────────
    memory_consolidator = MemoryConsolidator(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    # ── Workflow ──────────────────────────────────────────────────────────────
    workflow_store = WorkflowStore(db_pool=pool)
    workflow_planner = WorkflowPlanner(openrouter_client=openrouter_client, settings=settings)
    workflow_graph = build_workflow_graph(checkpointer=checkpointer)

    # The graph_config mirrors _make_workflow_config in ZeBot — passed to the scheduler
    # so scheduled workflow runs have access to all required services.
    workflow_graph_config = {
        "configurable": {
            "router": router,
            "capability_gate": capability_gate,
            "memory_store": memory_store,
            "persona_store": persona_store,
            "openrouter_client": openrouter_client,
            "embedder": embedder,
            "settings": settings,
            "workflow_store": workflow_store,
        }
    }

    bot = Bot(token=settings.telegram_bot_token)
    notifier = ProactiveNotifier(
        bot=bot,
        chat_id=int(settings.telegram_allowed_chat_id) if settings.telegram_allowed_chat_id else 0,
    )

    proactive_cfg = settings.proactive_config
    workflow_scheduler = WorkflowScheduler(
        workflow_store=workflow_store,
        workflow_graph=workflow_graph,
        graph_config=workflow_graph_config,
        settings=settings,
        pool=pool,
        notifier=notifier if proactive_cfg.get("alerts", {}).get("workflow_failure_enabled", True) else None,
    )

    reminder_store = ReminderStore(pool=pool)

    # Replay unsent reminders from before the last restart.
    # list_all_unsent (no fire_at filter) catches reminders that fired while the
    # server was down and were never delivered — fire them immediately via a task.
    now = datetime.now(timezone.utc)
    unsent_reminders = await reminder_store.list_all_unsent()
    overdue_count = 0
    for r in unsent_reminders:
        if r.fire_at <= now:
            asyncio.create_task(fire_reminder(reminder_store, notifier, r.id))
            overdue_count += 1
        else:
            workflow_scheduler.schedule_at(
                fn=lambda rid=r.id: fire_reminder(reminder_store, notifier, rid),
                dt=r.fire_at,
                job_id=f"user_reminder:{r.id}",
            )
    if unsent_reminders:
        log.info(
            "reminders_replayed",
            total=len(unsent_reminders),
            overdue=overdue_count,
            scheduled=len(unsent_reminders) - overdue_count,
        )

    bootstrap_agents(
        openrouter_client=openrouter_client,
        settings=settings,
        workflow_store=workflow_store,
        workflow_planner=workflow_planner,
        workflow_scheduler=workflow_scheduler,
        reminder_store=reminder_store,
        notifier=notifier,
        person_store=person_store,
        browser_client=browser_client,
        contact_channel_store=contact_channel_store,
        goal_store=goal_store,
        goal_planner=goal_planner,
        goal_executor=goal_executor,
        pool=pool,
    )
    graph = build_graph(checkpointer=checkpointer)

    await recover_stale_campaigns(pool, settings.prospecting_stale_timeout_minutes)
    log.info("stale_campaigns_checked")

    cost_reconciler = CostReconciler(pool=pool, sdk=openrouter_client._sdk)
    workflow_scheduler.schedule_job(
        fn=cost_reconciler.run,
        cron="*/15 * * * *",
        job_id="cost_reconciliation",
    )
    log.info("cost_reconciliation_scheduled")

    async def _sweep_active_goals() -> None:
        goals = await goal_store.list_for_advance()
        for g in goals:
            asyncio.create_task(goal_executor.advance(g.id))

    workflow_scheduler.schedule_job(
        fn=_sweep_active_goals,
        cron="*/15 * * * *",
        job_id="goal_advance_sweep",
    )
    log.info("goal_advance_sweep_scheduled")

    await workflow_scheduler.start()

    if settings.consolidation_enabled:
        nightly_cron = settings.consolidation_config.get("nightly_cron", "0 2 * * *")
        workflow_scheduler.schedule_job(
            fn=memory_consolidator.run,
            cron=nightly_cron,
            job_id="memory_consolidation",
        )
        log.info("consolidation_scheduled", cron=nightly_cron)

        contacts_cron = settings.contacts_config.get(
            "consolidation", {}
        ).get("nightly_cron", "0 3 * * *")
        workflow_scheduler.schedule_job(
            fn=contacts_consolidator.run,
            cron=contacts_cron,
            job_id="contacts_consolidation",
        )
        log.info("contacts_consolidation_scheduled", cron=contacts_cron)

        contact_review = ContactReviewNotifier(
            person_store=person_store,
            notifier=notifier,
        )
        review_cron = settings.contacts_config.get(
            "consolidation", {}
        ).get("review_cron", "30 8 * * *")
        workflow_scheduler.schedule_job(
            fn=contact_review.run,
            cron=review_cron,
            job_id="contact_review",
        )
        log.info("contact_review_scheduled", cron=review_cron)

        workflow_scheduler.schedule_job(
            fn=lambda: recover_stale_campaigns(pool, settings.prospecting_stale_timeout_minutes),
            cron="0 3 * * *",
            job_id="recover_stale_campaigns",
        )
        log.info("stale_campaign_recovery_scheduled")

    # ── Proactive push ────────────────────────────────────────────────────────
    morning_briefing = MorningBriefing(notifier=notifier, pool=pool, settings=settings)
    briefing_cfg = proactive_cfg.get("briefing", {})
    if briefing_cfg.get("enabled", True):
        briefing_cron = briefing_cfg.get("cron", "0 8 * * *")
        workflow_scheduler.schedule_job(
            fn=morning_briefing.run,
            cron=briefing_cron,
            job_id="morning_briefing",
        )
        log.info("briefing_scheduled", cron=briefing_cron)

    google_credentials = GoogleCredentials.from_settings(settings)

    email_channel = EmailChannel(credentials=google_credentials) if google_credentials else None
    channel_registry = ChannelRegistry(channels=[email_channel] if email_channel else [])
    contact_channel_store = ContactChannelStore(pool=pool)

    # ── Goal Engine ───────────────────────────────────────────────────────────
    goal_store = GoalStore(pool=pool)
    goal_planner = GoalPlanner(openrouter_client=openrouter_client, settings=settings)
    goal_executor = GoalExecutor(
        goal_store=goal_store,
        goal_planner=goal_planner,
        notifier=notifier,
    )

    calendar_reminders = CalendarReminderScheduler(
        notifier=notifier,
        pool=pool,
        openrouter_client=openrouter_client,
        workflow_scheduler=workflow_scheduler,
        google_credentials=google_credentials,
        settings=settings,
    )
    calendar_cfg = proactive_cfg.get("calendar", {})
    if calendar_cfg.get("sync_enabled", True):
        await calendar_reminders.start()
        workflow_scheduler.schedule_job(
            fn=calendar_reminders.sync,
            cron=calendar_cfg.get("sync_cron", "45 7 * * *"),
            job_id="calendar_reminder_sync",
        )
        log.info("calendar_reminders_scheduled")

    insight_engine = InsightEngine(
        notifier=notifier,
        pool=pool,
        openrouter_client=openrouter_client,
        settings=settings,
    )
    insights_proactive_cfg = proactive_cfg.get("insights", {})
    if insights_proactive_cfg.get("enabled", True):
        workflow_scheduler.schedule_job(
            fn=insight_engine.run,
            cron=insights_proactive_cfg.get("cron", "0 7 * * 0"),
            job_id="insight_generation",
        )
        log.info("insights_scheduled")

    if settings.telegram_bot_token and settings.public_url:
        await bot.set_webhook(
            url=f"{settings.public_url}/telegram/webhook",
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        log.info("telegram_webhook_registered", url=settings.public_url)

    whisper_model = settings.config.get("models", {}).get("whisper", "openai/whisper-1")
    transcription_client = TranscriptionClient(
        openrouter_client=openrouter_client,
        model=whisper_model,
        logger=get_logger("ze.transcription"),
    )

    locale = settings.persona_config.get("locale", "en")
    translations = ProgressTranslations.load(locale, settings.config_dir)

    ze_bot = ZeBot(
        bot=bot,
        graph=graph,
        workflow_graph=workflow_graph,
        store=ActiveSessionStore(),
        router=router,
        capability_gate=capability_gate,
        memory_store=memory_store,
        persona_store=persona_store,
        person_store=person_store,
        workflow_store=workflow_store,
        workflow_planner=workflow_planner,
        openrouter_client=openrouter_client,
        embedder=embedder,
        settings=settings,
        transcription_client=transcription_client,
        translations=translations,
        pool=pool,
        contact_channel_store=contact_channel_store,
        goal_store=goal_store,
        goal_executor=goal_executor,
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
        person_store=person_store,
        memory_consolidator=memory_consolidator,
        contacts_consolidator=contacts_consolidator,
        workflow_store=workflow_store,
        workflow_scheduler=workflow_scheduler,
        graph=graph,
        bot=bot,
        ze_bot=ze_bot,
        notifier=notifier,
        morning_briefing=morning_briefing,
        calendar_reminders=calendar_reminders,
        insight_engine=insight_engine,
        browser_client=browser_client,
        channel_registry=channel_registry,
        contact_channel_store=contact_channel_store,
        goal_store=goal_store,
        goal_executor=goal_executor,
    )
