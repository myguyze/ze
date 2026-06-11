from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from ze_api.bootstrap import bootstrap_agents, prepare_gate_registry
from ze_browser import BrowserClient
from ze_notifications.ntfy import NtfyConfig, NtfyNotifier
from ze_notifications.notifier import Notifier as PushNotifier
from ze_core.capability.gate import CapabilityGate
from ze_core.capability.overrides import PostgresCapabilityOverrideStore
from ze_core.channels.registry import ChannelRegistry
from ze_personal.contacts.channel_store import ContactChannelStore
from ze_api.db import create_checkpointer_pool, create_pool, dispose_checkpointer_pool
from ze_core.embeddings import get_embedder
from ze_core.messages.store import PostgresMessageStore
from ze_core.orchestration.registry import get_agent
from ze_personal.goals.executor import GoalExecutor
from ze_personal.goals.planner import GoalPlanner
from ze_personal.goals.postgres import PostgresGoalStore as GoalStore
from ze_google.auth import GoogleCredentials
from ze_api.logging import get_logger
from ze_personal.contacts.consolidator import ContactsConsolidator
from ze_personal.contacts.store import PersonStore
from ze_memory.consolidator import MemoryConsolidator
from ze_memory.graph import PostgresGraphStore
from ze_memory.retriever import PostgresMemoryStore
from ze_personal.persona.postgres import PostgresPersonaStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.orchestration.graph import build_graph
from ze_personal.graph.workflow import build_workflow_graph
from ze_core.progress import ProgressTranslations
from ze_calendar.reminders.store import ReminderStore, fire_reminder
from ze_personal.goals.suggestion_store import GoalSuggestionStore
from ze_core.proactive.push_log_store import PushLogStore
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.proactive.scheduler import ProactiveScheduler
from ze_calendar.reminders.calendar_store import CalendarReminderStore
from ze_calendar.reminders.calendar import CalendarReminderService
from ze_calendar.jobs.calendar_reminder import CalendarReminderJob
from ze_core.routing.complexity import ComplexityEstimator
from ze_core.routing.router import EmbeddingRouter
from ze_core.routing.store import PostgresRoutingStore
from ze_core.routing.types import RouterConfig
from ze_api.settings import Settings, get_settings
from ze_core.conversation import TurnResult, invoke_raw_turn, resume_turn
from ze_api.interface.native import NativeAppInterface
from ze_api.api.ws import ConnectionManager
from ze_api.api.pending_confirmations import PendingConfirmationStore
from ze_core.interface.types import RawInput
from ze_core.interface.validation import validate_interface
from ze_core.telemetry.reconciler import CostReconciler
from ze_core.telemetry.tracker import CostTracker
from ze_core.telemetry.postgres import PostgresCostStore
from ze_personal.workflow.planner import WorkflowPlanner
from ze_personal.workflow.postgres import PostgresWorkflowStore
from ze_personal.workflow.store import WorkflowStore
from ze_personal.workflow.scheduler import WorkflowScheduler
from ze_core.container import Container as CoreContainer
from ze_core.orchestration.hooks import register_hook
from ze_api.hooks import ComponentCollectionHook, ToolCallCapHook
from ze_personal.plugin import PersonalPlugin
from ze_calendar.plugin import CalendarPlugin
from ze_email.plugin import EmailPlugin
from ze_prospecting.plugin import ProspectingPlugin
from ze_prospecting.types import ProspectingSettings
import ze_components.tools  # noqa: F401 — registers all render tools at import time

log = get_logger(__name__)


@dataclass(kw_only=True)
class ZeContainer(CoreContainer):
    """Ze application container — ze-core graph stack plus WebSocket, proactive, workflow."""

    persona_store: Any
    person_store: PersonStore
    contacts_consolidator: ContactsConsolidator
    workflow_store: WorkflowStore
    workflow_planner: WorkflowPlanner
    workflow_scheduler: WorkflowScheduler
    proactive_scheduler: ProactiveScheduler
    notifier: ProactiveNotifier
    calendar_reminders: CalendarReminderJob
    goal_suggestion_store: GoalSuggestionStore
    browser_client: BrowserClient
    channel_registry: ChannelRegistry
    contact_channel_store: ContactChannelStore
    goal_store: GoalStore
    goal_executor: GoalExecutor
    prospecting_plugin: ProspectingPlugin
    personal_plugin: PersonalPlugin
    push_notifier: NtfyNotifier | None
    message_store: PostgresMessageStore
    connection_manager: ConnectionManager
    component_hook: ComponentCollectionHook
    confirmation_store: PendingConfirmationStore

    def _build_config(self, session_id: str, **configurable_extra: object) -> dict:
        plugin_services: dict = {}
        for plugin in self.plugins:
            plugin_services.update(plugin.configurable_services())

        from ze_memory.extractor import gather_fact_proposals

        configurable: dict = {
            "thread_id": str(session_id),
            "router": self.router,
            "capability_gate": self.capability_gate,
            "memory_store": self.memory_store,
            "fact_extractor": gather_fact_proposals,
            "persona_store": self.persona_store,
            "person_store": self.person_store,
            "openrouter_client": self.openrouter_client,
            "embedder": self.embedder,
            "settings": self.settings,
            "workflow_planner": self.workflow_planner,
            "contact_channel_store": self.contact_channel_store,
            "goal_store": self.goal_store,
            "interface": self.interface,
            "component_hook": self.component_hook,
            **plugin_services,
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
        return await invoke_raw_turn(self, session_id, raw, config_extra=config_extra)

    async def resume_turn(self, config: dict) -> TurnResult:
        return await resume_turn(self, config)

    async def close(self) -> None:
        await self.proactive_scheduler.stop()
        await self.workflow_scheduler.stop()
        await self.browser_client.close()
        await self.prospecting_plugin.campaign_store.fail_all_running()
        if self.push_notifier is not None:
            await self.push_notifier._session.close()
        await super().close()

    @classmethod
    async def from_config(
        cls,
        config_dir: Path | None = None,
        *,
        interface: Any | None = None,
    ) -> ZeContainer:
        get_settings.cache_clear()
        settings = Settings(config_dir=config_dir) if config_dir else Settings()
        container = await build_container(settings)
        if interface is not None:
            container.interface = interface
            validate_interface(interface)
        return container


Container = ZeContainer


async def build_container(settings: Settings) -> ZeContainer:
    pool = await create_pool(settings)
    checkpointer_pool = await create_checkpointer_pool(settings)
    embedder = get_embedder()
    core_settings = settings.to_core_settings()
    prospecting_settings = ProspectingSettings(
        max_iterations=settings.prospecting_max_iterations,
        max_loop_tokens=settings.prospecting_max_loop_tokens,
        stale_timeout_minutes=settings.prospecting_stale_timeout_minutes,
        browser_delay_ms=settings.browser_delay_ms,
        browser_max_text_chars=settings.browser_max_text_chars,
    )

    serde = JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("ze_core.routing.types", "SubTask"),
            ("ze_core.routing.types", "RoutingEnvelope"),
            ("ze_core.orchestration.types", "ToolCall"),
            ("ze_core.orchestration.types", "AgentResult"),
            ("ze_core.orchestration.types", "AgentContext"),
            ("ze_core.capability.types", "GateDecision"),
            ("ze_memory.types", "MemoryContext"),
            ("ze_memory.types", "Fact"),
            ("ze_memory.types", "Episode"),
            ("ze_memory.types", "ProfileFacet"),
            ("ze_personal.contacts.types", "Person"),
            ("ze_personal.contacts.types", "PersonContext"),
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

    graph_store = PostgresGraphStore(pool=pool)
    memory_store = PostgresMemoryStore(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
        graph_store=graph_store,
    )

    browser_client = BrowserClient(
        base_url=settings.browser_service_url,
        timeout=settings.browser_timeout_seconds,
    )

    push_notifier: NtfyNotifier | None = None
    if settings.ntfy_topic:
        import aiohttp as _aiohttp
        _ntfy_config = NtfyConfig(
            base_url=settings.ntfy_base_url,
            topic=settings.ntfy_topic,
            token=settings.ntfy_token or None,
        )
        _ntfy_session = _aiohttp.ClientSession()
        push_notifier = NtfyNotifier(config=_ntfy_config, session=_ntfy_session)
        log.info("ntfy_notifier_registered", topic=settings.ntfy_topic)

    message_store = PostgresMessageStore(pool=pool)
    connection_manager = ConnectionManager()
    confirmation_store = PendingConfirmationStore(pool=pool)

    interface = NativeAppInterface(
        message_store=message_store,
        connection_manager=connection_manager,
        notifier=push_notifier,
    )
    validate_interface(interface)
    notifier = ProactiveNotifier(interface=interface)

    persona_cfg = settings.persona_config
    persona_store = PostgresPersonaStore(
        pool=pool,
        profiles=persona_cfg.get("profiles", {}),
        default_profile=persona_cfg.get("profile", "default"),
    )
    person_store = PersonStore(pool=pool, memory_store=memory_store)
    contacts_consolidator = ContactsConsolidator(
        pool=pool,
        person_store=person_store,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    memory_consolidator = MemoryConsolidator(
        store=memory_store,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

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
    override_store = PostgresCapabilityOverrideStore(pool=pool)
    capability_gate = CapabilityGate(override_store=override_store)
    await capability_gate.load_persistent_overrides()

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
            "workflow_planner": workflow_planner,
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
    goal_planner = GoalPlanner(client=openrouter_client, model=settings.workflow_plan_model, memory_store=memory_store)
    goal_executor = GoalExecutor(
        goal_store=goal_store,
        goal_planner=goal_planner,
        push=notifier.push_notification,
        agent_getter=get_agent,
        memory_store=memory_store,
    )
    proactive_scheduler = ProactiveScheduler()
    reminder_store = ReminderStore(pool=pool)
    push_log_store = PushLogStore(pool=pool)
    goal_suggestion_store = GoalSuggestionStore(pool=pool)

    google_credentials = GoogleCredentials.from_settings(settings)
    prospecting_plugin = ProspectingPlugin(pool=pool, prospecting_settings=prospecting_settings)
    email_plugin = EmailPlugin(google_credentials=google_credentials)

    news_cfg = settings.config.get("news", {})
    news_store = None
    news_fetch_job = None
    news_source_configs = []
    if news_cfg.get("enabled", True) and news_cfg.get("sources"):
        from ze_news.jobs.fetch import NewsFetchJob
        from ze_news.plugin import NewsPlugin
        from ze_news.registry import build_registry
        from ze_news.store import NewsStore
        from ze_news.types import SourceConfig

        news_source_configs = [
            SourceConfig(key=s["key"], type=s["type"], url=s["url"], tags=s.get("tags", []))
            for s in news_cfg["sources"]
        ]
        news_registry = build_registry(news_source_configs)
        news_store = NewsStore(pool=pool, embedder=embedder)
        news_credibility_cfg = news_cfg.get("credibility", {})
        news_fetch_job = NewsFetchJob(
            registry=news_registry,
            store=news_store,
            retention_days=int(news_cfg.get("retention_days", 7)),
            client=openrouter_client if news_credibility_cfg.get("enabled", False) else None,
            credibility_enabled=news_credibility_cfg.get("enabled", False),
            credibility_llm_enabled=news_credibility_cfg.get("llm_scoring", True),
            credibility_model=news_credibility_cfg.get("model", "openai/gpt-4o-mini"),
        )

    personal_plugin = PersonalPlugin(
        notifier=notifier,
        push_log_store=push_log_store,
        memory_store=memory_store,
        workflow_store=workflow_store,
        person_store=person_store,
        settings=core_settings,
        goal_store=goal_store,
        goal_planner=goal_planner,
        suggestion_store=goal_suggestion_store,
        openrouter_client=openrouter_client,
        pool=pool,
        news_store=news_store,
    )

    plugins: list = [personal_plugin, CalendarPlugin(), email_plugin, prospecting_plugin]
    if news_store is not None:
        from ze_news.plugin import NewsPlugin
        news_plugin = NewsPlugin(registry=news_registry, store=news_store, fetch_job=news_fetch_job)
        plugins.append(news_plugin)
        log.info("news_plugin_registered", sources=len(news_source_configs))

    bootstrap_agents(
        openrouter_client=openrouter_client,
        settings=settings,
        google_credentials=google_credentials,
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
        campaign_store=prospecting_plugin.campaign_store,
        prospecting_settings=prospecting_settings,
        plugins=plugins,
        memory_store=memory_store,
        news_store=news_store,
    )
    component_hook = ComponentCollectionHook()
    register_hook(component_hook)
    log.info("component_collection_hook_registered")

    register_hook(ToolCallCapHook(max_tool_calls=settings.max_tool_calls_per_turn))
    log.info("tool_call_cap_hook_registered", max_tool_calls=settings.max_tool_calls_per_turn)

    graph = build_graph(checkpointer=checkpointer, plugins=plugins)
    workflow_graph = build_workflow_graph(checkpointer=checkpointer, plugins=plugins)

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

    await prospecting_plugin.recover_stale_on_startup()
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

    for plugin in plugins:
        plugin.register_proactive_jobs(
            proactive_scheduler,
            core_settings,
            consolidation_enabled=settings.consolidation_enabled,
        )

    proactive_cfg = settings.proactive_config
    gmail_channel = email_plugin.gmail_channel
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

    if news_store is not None and news_fetch_job is not None:
        fetch_cron = news_cfg.get("fetch_schedule", "*/30 * * * *")
        proactive_scheduler.register(news_fetch_job, cron=fetch_cron)
        log.info("news_fetch_scheduled", cron=fetch_cron, sources=len(news_source_configs))

    await proactive_scheduler.start()

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
        notifier=notifier,
        calendar_reminders=calendar_reminders,
        goal_suggestion_store=goal_suggestion_store,
        browser_client=browser_client,
        channel_registry=channel_registry,
        contact_channel_store=contact_channel_store,
        goal_store=goal_store,
        goal_executor=goal_executor,
        prospecting_plugin=prospecting_plugin,
        personal_plugin=personal_plugin,
        push_notifier=push_notifier,
        message_store=message_store,
        connection_manager=connection_manager,
        component_hook=component_hook,
        confirmation_store=confirmation_store,
        plugins=plugins,
    )
    return container
