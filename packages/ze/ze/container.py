from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram import Bot
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from ze.agents.bootstrap import bootstrap_agents, prepare_gate_registry
from ze_browser import BrowserClient
from ze_core.capability.gate import CapabilityGate
from ze_core.capability.overrides import PostgresCapabilityOverrideStore
from ze.google.gmail import GmailChannel
from ze_core.channels.registry import ChannelRegistry
from ze_core.contacts.channel_store import ContactChannelStore
from ze.db import create_checkpointer_pool, create_pool, dispose_checkpointer_pool
from ze_core.embeddings import get_embedder
from ze_core.orchestration.registry import get_agent
from ze_core.goals.executor import GoalExecutor
from ze_core.goals.planner import GoalPlanner
from ze_core.goals.postgres import PostgresGoalStore as GoalStore
from ze.google.auth import GoogleCredentials
from ze.logging import get_logger
from ze_core.contacts.consolidator import ContactsConsolidator
from ze_core.contacts.store import PersonStore
from ze.jobs.contacts import ContactReviewNotifier
from ze.jobs.prospecting import recover_stale_campaigns
from ze_core.memory.consolidator import MemoryConsolidator
from ze_core.memory.postgres import PostgresMemoryStore
from ze_core.persona.postgres import PostgresPersonaStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.orchestration.graph import build_graph, build_workflow_graph
from ze_core.progress import ProgressTranslations
from ze.reminders.store import ReminderStore, fire_reminder
from ze.jobs.briefing import MorningBriefing
from ze_core.proactive.push_log_store import PushLogStore
from ze.jobs.insights import InsightEngine
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.proactive.scheduler import ProactiveScheduler
from ze.reminders.calendar_store import CalendarReminderStore
from ze.reminders.calendar import CalendarReminderService
from ze.jobs.calendar import CalendarReminderJob
from ze_core.routing.complexity import ComplexityEstimator
from ze_core.routing.router import EmbeddingRouter
from ze_core.routing.store import PostgresRoutingStore
from ze_core.routing.types import RouterConfig
from ze.settings import Settings, get_settings
from ze_core.conversation import TurnResult, invoke_raw_turn, resume_turn
from ze.telegram.app_interface import TelegramAppInterface
from ze_core.interface.types import RawInput
from ze.telegram.bot import ZeBot
from ze.telegram.session import ActiveSessionStore
from ze_core.interface.validation import validate_interface
from ze_core.telemetry.reconciler import CostReconciler
from ze_core.telemetry.tracker import CostTracker
from ze_core.telemetry.postgres import PostgresCostStore
from ze_core.workflow.planner import WorkflowPlanner
from ze_core.workflow.postgres import PostgresWorkflowStore
from ze_core.workflow.store import WorkflowStore
from ze_core.workflow.scheduler import WorkflowScheduler
from ze_core.container import Container as CoreContainer

log = get_logger(__name__)


@dataclass(kw_only=True)
class ZeContainer(CoreContainer):
    """Ze application container — ze-core graph stack plus Telegram, proactive, workflow."""

    # ── Ze-only resources (framework fields live on CoreContainer) ─────────────
    persona_store: PersonaStore
    person_store: PersonStore
    contacts_consolidator: ContactsConsolidator
    workflow_store: WorkflowStore
    workflow_planner: WorkflowPlanner
    workflow_scheduler: WorkflowScheduler
    proactive_scheduler: ProactiveScheduler
    bot: Bot
    ze_bot: ZeBot
    notifier: ProactiveNotifier
    morning_briefing: MorningBriefing
    calendar_reminders: CalendarReminderJob
    insight_engine: InsightEngine
    browser_client: BrowserClient
    channel_registry: ChannelRegistry
    contact_channel_store: ContactChannelStore
    goal_store: GoalStore
    goal_executor: GoalExecutor

    def _build_config(self, session_id: str, **configurable_extra: object) -> dict:
        configurable: dict = {
            "thread_id": str(session_id),
            "router": self.router,
            "capability_gate": self.capability_gate,
            "memory_store": self.memory_store,
            "persona_store": self.persona_store,
            "person_store": self.person_store,
            "openrouter_client": self.openrouter_client,
            "embedder": self.embedder,
            "settings": self.settings,
            "workflow_planner": self.workflow_planner,
            "contact_channel_store": self.contact_channel_store,
            "interface": self.interface,
        }
        configurable.update(configurable_extra)
        return {"configurable": configurable}

    async def invoke_raw_turn(
        self,
        session_id: str,
        raw: RawInput,
        *,
        config_extra: dict | None = None,
    ) -> TurnResult:
        """Run one conversation turn from transport-layer input (Ze graph + state)."""
        return await invoke_raw_turn(self, session_id, raw, config_extra=config_extra)

    async def resume_turn(self, config: dict) -> TurnResult:
        """Resume after capability confirmation (LangGraph interrupt)."""
        return await resume_turn(self, config)

    async def close(self) -> None:
        await self.proactive_scheduler.stop()
        await self.workflow_scheduler.stop()
        await self.bot.session.close()
        await self.browser_client.close()
        await super().close()

    @classmethod
    async def from_config(
        cls,
        config_dir: Path | None = None,
        *,
        interface: Any | None = None,
    ) -> ZeContainer:
        """Build the Ze container; discovers agents via ``bootstrap_agents()``."""
        get_settings.cache_clear()
        settings = Settings(config_dir=config_dir) if config_dir else Settings()
        container = await build_container(settings)
        if interface is not None:
            container.interface = interface
            validate_interface(interface)
        return container


# Backward-compatible alias.
Container = ZeContainer


async def build_container(settings: Settings) -> ZeContainer:
    pool = await create_pool(settings)
    checkpointer_pool = await create_checkpointer_pool(settings)
    embedder = get_embedder()

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("ze_core.routing.types", "SubTask"),
            ("ze_core.routing.types", "RoutingEnvelope"),
            ("ze_core.orchestration.types", "ToolCall"),
            ("ze_core.orchestration.types", "AgentResult"),
            ("ze_core.orchestration.types", "AgentContext"),
            ("ze_core.capability.types", "GateDecision"),
            ("ze_core.memory.types", "MemoryContext"),
            ("ze_core.memory.types", "UserFact"),
            ("ze_core.memory.types", "Episode"),
            ("ze_core.memory.types", "UserProfile"),
            ("ze_core.contacts.types", "Person"),
            ("ze_core.contacts.types", "PersonContext"),
            ("asyncpg.pgproto.pgproto", "UUID"),
        ]
    )
    checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=serde)
    await checkpointer.setup()

    cost_store = PostgresCostStore(pool=pool)
    cost_tracker = CostTracker(store=cost_store)

    openrouter_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        logger=get_logger("ze.openrouter"),
        http_referer=settings.openrouter_http_referer,
        title=settings.openrouter_title,
        cost_tracker=cost_tracker,
    )

    memory_store = PostgresMemoryStore(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    browser_client = BrowserClient(
        base_url=settings.browser_service_url,
        timeout=settings.browser_timeout_seconds,
    )

    persona_cfg = settings.persona_config
    persona_store = PostgresPersonaStore(
        pool=pool,
        profiles=persona_cfg.get("profiles", {}),
        default_profile=persona_cfg.get("profile", "default"),
    )
    person_store = PersonStore(pool=pool)
    contacts_consolidator = ContactsConsolidator(
        pool=pool,
        person_store=person_store,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    # ── Memory consolidation ──────────────────────────────────────────────────
    memory_consolidator = MemoryConsolidator(
        store=memory_store,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    # ── Workflow ──────────────────────────────────────────────────────────────
    workflow_store = PostgresWorkflowStore(db_pool=pool)
    workflow_planner = WorkflowPlanner(openrouter_client=openrouter_client)

    prepare_gate_registry(settings)
    estimator = ComplexityEstimator()
    router = EmbeddingRouter(
        embedder=embedder,
        openrouter_client=openrouter_client,
        routing_store=PostgresRoutingStore(pool),
        config=RouterConfig(),
        estimator=estimator,
    )
    workflow_graph = build_workflow_graph(checkpointer=checkpointer)
    override_store = PostgresCapabilityOverrideStore(pool=pool)
    capability_gate = CapabilityGate(override_store=override_store)
    await capability_gate.load_persistent_overrides()

    bot = Bot(token=settings.telegram_bot_token)
    telegram_chat_id = (
        int(settings.telegram_allowed_chat_id)
        if settings.telegram_allowed_chat_id
        else 0
    )
    interface = TelegramAppInterface(bot=bot, chat_id=telegram_chat_id)
    validate_interface(interface)
    notifier = ProactiveNotifier(interface=interface)

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

    _wf_push_log = PushLogStore(pool=pool)

    async def _workflow_executor(workflow, execution_id):
        from ze_core.telemetry.context import set_flow_context
        set_flow_context("workflow_execution", session_id=f"workflow:{workflow.id}")
        initial_state = {
            "prompt": f"[workflow] {workflow.name}",
            "session_id": f"workflow:{workflow.id}",
            "session_overrides": {},
            "envelope": None,
            "memory_context": None,
            "agent_context": None,
            "gate_decision": None,
            "agent_result": None,
            "subtask_results": [],
            "pending_confirmation": False,
            "messages": [],
            "last_active_at": None,
            "workflow_id": workflow.id,
            "workflow_execution_id": execution_id,
            "workflow_steps": workflow.steps,
            "current_step_index": 0,
            "workflow_step_results": [],
            "final_response": None,
            "error": None,
        }
        run_config = {
            **workflow_graph_config,
            "configurable": {
                **workflow_graph_config.get("configurable", {}),
                "thread_id": str(execution_id),
                "workflow_store": workflow_store,
            },
        }
        await workflow_graph.ainvoke(initial_state, run_config)

    async def _workflow_failure_handler(workflow, exc):
        alerts_cfg = settings.proactive_config.get("alerts", {})
        if not alerts_cfg.get("workflow_failure_enabled", True):
            return
        cooldown = int(alerts_cfg.get("workflow_failure_cooldown_hours", 1))
        event_type = f"workflow_failure:{workflow.id}"
        if await _wf_push_log.was_sent_within_hours(event_type, cooldown):
            log.info("failure_alert_suppressed_cooldown", workflow=workflow.name)
            return
        await notifier.push(
            f"Workflow failed: *{workflow.name}*\n`{str(exc)[:200]}`",
            format="markdown",
            urgency="high",
        )
        await _wf_push_log.log(event_type, workflow.name)
        log.info("failure_alert_sent", workflow=workflow.name)

    workflow_scheduler = WorkflowScheduler(
        workflow_store=workflow_store,
        executor=_workflow_executor,
        enabled=settings.scheduler_enabled,
        on_failure=_workflow_failure_handler,
    )

    contact_channel_store = ContactChannelStore(pool=pool)
    goal_store = GoalStore(pool=pool)
    goal_planner = GoalPlanner(client=openrouter_client, model=settings.workflow_plan_model)
    goal_executor = GoalExecutor(
        goal_store=goal_store,
        goal_planner=goal_planner,
        push=notifier.push_notification,
        agent_getter=get_agent,
    )
    proactive_scheduler = ProactiveScheduler()
    reminder_store = ReminderStore(pool=pool)

    bootstrap_agents(
        openrouter_client=openrouter_client,
        settings=settings,
        pool=pool,
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
    )

    graph = build_graph(checkpointer=checkpointer)

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

    await recover_stale_campaigns(pool, settings.prospecting_stale_timeout_minutes)
    log.info("stale_campaigns_checked")

    cost_reconciler = CostReconciler(store=cost_store, openrouter_client=openrouter_client)
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

    proactive_scheduler.add_cron_job(
        fn=_sweep_active_goals,
        cron="*/15 * * * *",
        job_id="goal_advance_sweep",
    )
    log.info("goal_advance_sweep_scheduled")

    await workflow_scheduler.start()

    if settings.consolidation_enabled:
        nightly_cron = settings.consolidation_config.get("nightly_cron") or "0 2 * * *"
        proactive_scheduler.add_cron_job(
            fn=memory_consolidator.run,
            cron=nightly_cron,
            job_id="memory_consolidation",
        )
        log.info("consolidation_scheduled", cron=nightly_cron)

        contacts_cron = settings.contacts_config.get(
            "consolidation", {}
        ).get("nightly_cron", "0 3 * * *")
        proactive_scheduler.add_cron_job(
            fn=contacts_consolidator.run,
            cron=contacts_cron,
            job_id="contacts_consolidation",
        )
        log.info("contacts_consolidation_scheduled", cron=contacts_cron)

        contact_review = ContactReviewNotifier(
            person_store=person_store,
            notifier=notifier,
        )
        review_cron = settings.contacts_config.get("consolidation", {}).get("review_cron", "30 8 * * *")
        proactive_scheduler.register(contact_review, cron=review_cron)
        log.info("contact_review_scheduled", cron=review_cron)

        proactive_scheduler.add_cron_job(
            fn=lambda: recover_stale_campaigns(pool, settings.prospecting_stale_timeout_minutes),
            cron="0 3 * * *",
            job_id="recover_stale_campaigns",
        )
        log.info("stale_campaign_recovery_scheduled")

    # ── Proactive push ────────────────────────────────────────────────────────
    proactive_cfg = settings.proactive_config
    push_log_store = PushLogStore(pool=pool)
    morning_briefing = MorningBriefing(
        notifier=notifier,
        push_log_store=push_log_store,
        memory_store=memory_store,
        workflow_store=workflow_store,
        person_store=person_store,
        settings=settings,
    )
    briefing_cfg = proactive_cfg.get("briefing", {})
    if briefing_cfg.get("enabled", True):
        proactive_scheduler.register(morning_briefing, cron=briefing_cfg.get("cron", "0 8 * * *"))
        log.info("briefing_scheduled", cron=briefing_cfg.get("cron", "0 8 * * *"))

    google_credentials = GoogleCredentials.from_settings(settings)

    gmail_channel = GmailChannel(credentials=google_credentials) if google_credentials else None
    channel_registry = ChannelRegistry(channels=[gmail_channel] if gmail_channel else [])

    calendar_reminder_store = CalendarReminderStore(pool=pool)
    calendar_reminder_service = CalendarReminderService(
        notifier=notifier,
        store=calendar_reminder_store,
        push_log_store=push_log_store,
        openrouter_client=openrouter_client,
        scheduler=workflow_scheduler,
        settings=settings,
    )
    calendar_reminders = CalendarReminderJob(
        service=calendar_reminder_service,
        credentials=google_credentials,
    )
    calendar_cfg = proactive_cfg.get("calendar", {})
    if calendar_cfg.get("sync_enabled", True):
        await calendar_reminder_service.replay_unsent()
        proactive_scheduler.register(calendar_reminders, cron=calendar_cfg.get("sync_cron", "45 7 * * *"))
        log.info("calendar_reminders_scheduled")

    insight_engine = InsightEngine(
        notifier=notifier,
        pool=pool,
        openrouter_client=openrouter_client,
        settings=settings,
    )
    insights_proactive_cfg = proactive_cfg.get("insights", {})
    if insights_proactive_cfg.get("enabled", True):
        proactive_scheduler.register(insight_engine, cron=insights_proactive_cfg.get("cron", "0 7 * * 0"))
        log.info("insights_scheduled")

    await proactive_scheduler.start()

    if settings.telegram_bot_token and settings.public_url:
        await bot.set_webhook(
            url=f"{settings.public_url}/telegram/webhook",
            secret_token=settings.telegram_webhook_secret,
            allowed_updates=["message", "callback_query"],
        )
        log.info("telegram_webhook_registered", url=settings.public_url)

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
        translations=translations,
        pool=pool,
        contact_channel_store=contact_channel_store,
        goal_store=goal_store,
        goal_executor=goal_executor,
        interface=interface,
    )

    container = ZeContainer(
        settings=settings,
        pool=pool,
        checkpointer_pool=checkpointer_pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        router=router,
        capability_gate=capability_gate,
        memory_store=memory_store,
        memory_consolidator=memory_consolidator,
        graph=graph,
        interface=interface,
        persona_store=persona_store,
        person_store=person_store,
        contacts_consolidator=contacts_consolidator,
        workflow_store=workflow_store,
        workflow_planner=workflow_planner,
        workflow_scheduler=workflow_scheduler,
        proactive_scheduler=proactive_scheduler,
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
    ze_bot.bind_container(container)
    return container
