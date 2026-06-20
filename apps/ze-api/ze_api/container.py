from __future__ import annotations

import asyncpg
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from ze_api.bootstrap import bootstrap_agents, build_integrations, _load_plugin_classes, _instantiate_plugins
from ze_browser import BrowserClient
from ze_notifications.ntfy import NtfyConfig, NtfyNotifier
from ze_core.capability.gate import CapabilityGate
from ze_core.capability.overrides import PostgresCapabilityOverrideStore
from ze_plugin.channels.registry import ChannelRegistry
from ze_api.db import create_checkpointer_pool, create_pool
from ze_core.embeddings import get_embedder
from ze_core.messages.store import PostgresMessageStore
from ze_api.sessions.store import PostgresSessionStore
from ze_api.logging import get_logger
from ze_memory.consolidator import MemoryConsolidator
from ze_memory.session_summary import SessionSummariser
from ze_memory.graph import PostgresGraphStore
from ze_memory.retriever import PostgresMemoryStore
from ze_personal.persona.postgres import PostgresPersonaStore
from ze_personal.workflow.postgres import PostgresWorkflowStore
from ze_personal.workflow.scheduler import WorkflowScheduler
from ze_personal.workflow.store import WorkflowStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.orchestration.graph import build_graph
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_proactive.scheduler import ProactiveScheduler
from ze_correlation import CorrelationEngine, CorrelationJob, CorrelationPushConsumer, PostgresHypothesisStore
from ze_memory.relevance import RelevanceModel
from ze_core.routing.complexity import ComplexityEstimator
from ze_core.routing.router import EmbeddingRouter
from ze_core.routing.store import PostgresRoutingStore
from ze_core.routing.types import RouterConfig
from ze_api.settings import Settings, get_settings
from ze_core.conversation import TurnResult, invoke_raw_turn, resume_turn
from ze_api.interface.native import NativeAppInterface
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.pending_confirmations import PendingConfirmationStore
from ze_onboarding import (
    CoreOnboardingProvider,
    OnboardingCoordinator,
    PostgresOnboardingPersistence as OnboardingPersistence,
    PostgresOnboardingStore as OnboardingStore,
    ResetService,
)
from ze_agents.interface.types import RawInput
from ze_agents.interface.validation import validate_interface
from ze_core.telemetry.reconciler import CostReconciler
from ze_core.telemetry.tracker import CostTracker
from ze_core.telemetry.postgres import PostgresCostStore
from ze_core.container import Container as CoreContainer
from ze_agents.hooks import register_hook
from ze_api.hooks import ComponentCollectionHook, ToolCallCapHook
import ze_components.tools  # noqa: F401 — registers all render tools at import time

log = get_logger(__name__)


@dataclass(kw_only=True)
class ZeContainer(CoreContainer):
    """Ze application container — ze-core graph stack plus WebSocket, proactive, workflow."""

    translations: Any  # ProgressTranslations — built from merged plugin locale data
    signal_sources: dict  # source_key → SignalSource; collected from all plugins
    correlation_engine: CorrelationEngine | None
    persona_store: Any
    workflow_store: WorkflowStore
    _plugin_stores: dict  # keyed store name → store; populated from plugin.rest_stores()
    workflow_scheduler: WorkflowScheduler
    proactive_scheduler: ProactiveScheduler
    browser_client: BrowserClient
    push_notifier: NtfyNotifier | None
    message_store: PostgresMessageStore
    session_store: PostgresSessionStore
    connection_manager: ConnectionManager
    component_hook: ComponentCollectionHook
    confirmation_store: PendingConfirmationStore
    onboarding_coordinator: OnboardingCoordinator
    reset_service: ResetService
    _checkpointer: Any  # AsyncPostgresSaver — exposed for plugin startup()
    _push_log_store: Any  # PushLogStore — exposed for PersonalPlugin startup()
    data_portability_service: Any  # DataPortabilityService

    def _build_config(self, thread_id: str, **configurable_extra: object) -> dict:
        plugin_services: dict = {}
        for plugin in self.plugins:
            plugin_services.update(plugin.configurable_services())

        from ze_memory.extractor import gather_fact_proposals

        configurable: dict = {
            "thread_id": str(thread_id),
            "router": self.router,
            "capability_gate": self.capability_gate,
            "memory_store": self.memory_store,
            "fact_extractor": gather_fact_proposals,
            "persona_store": self.persona_store,
            "openrouter_client": self.openrouter_client,
            "embedder": self.embedder,
            "settings": self.settings,
            "interface": self.interface,
            "component_hook": self.component_hook,
            "correlation_engine": self.correlation_engine,
            **plugin_services,
        }
        configurable.update(configurable_extra)
        return {"configurable": configurable}

    async def invoke_raw_turn(
        self,
        thread_id: str,
        raw: RawInput,
        *,
        config_extra: dict | None = None,
    ) -> TurnResult:
        return await invoke_raw_turn(self, thread_id, raw, config_extra=config_extra)

    async def resume_turn(self, config: dict) -> TurnResult:
        return await resume_turn(self, config)

    async def close(self) -> None:
        for plugin in reversed(self.plugins):
            try:
                await plugin.shutdown()
            except Exception as exc:
                log.warning(
                    "plugin_shutdown_failed",
                    plugin=type(plugin).__name__,
                    error=str(exc),
                )
        await self.proactive_scheduler.stop()
        await self.workflow_scheduler.stop()
        await self.browser_client.close()
        if self.push_notifier is not None:
            await self.push_notifier.close()
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


def collect_plugin_signal_sources(plugins: list) -> dict:
    """Collect and deduplicate SignalSources from all plugins.

    Raises ``AgentConfigError`` on duplicate ``source_key``, matching the
    duplicate-key rule for memory policies.
    """
    from ze_agents.errors import AgentConfigError

    sources: dict = {}
    for plugin in plugins:
        for source in plugin.signal_sources():
            if source.source_key in sources:
                raise AgentConfigError(
                    f"Duplicate signal source key {source.source_key!r} "
                    f"contributed by {type(plugin).__name__}"
                )
            sources[source.source_key] = source
    return sources


async def build_container(settings: Settings) -> ZeContainer:
    from sentence_transformers import SentenceTransformer
    from ze_agents.client import LLMClient
    from ze_agents.settings import Settings as CoreSettings

    pool = await create_pool(settings)
    checkpointer_pool = await create_checkpointer_pool(settings)
    embedder = get_embedder()
    core_settings = settings.to_core_settings()

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

    hypothesis_store = PostgresHypothesisStore(pool=pool)
    relevance_model = RelevanceModel(memory_store=memory_store)
    correlation_engine = CorrelationEngine(
        memory_store=memory_store,
        relevance_model=relevance_model,
        llm_client=openrouter_client,
        hypothesis_store=hypothesis_store,
        settings=settings,
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
    session_store = PostgresSessionStore(pool=pool)
    connection_manager = ConnectionManager()
    confirmation_store = PendingConfirmationStore(pool=pool)

    interface = NativeAppInterface(
        message_store=message_store,
        connection_manager=connection_manager,
        notifier=push_notifier,
    )
    validate_interface(interface)

    notifier = ProactiveNotifier(interface=interface)
    push_log_store = PushLogStore(pool=pool)

    persona_cfg = settings.persona_config
    persona_store = PostgresPersonaStore(
        pool=pool,
        profiles=persona_cfg.get("profiles", {}),
        default_profile=persona_cfg.get("profile", "default"),
    )

    memory_consolidator = MemoryConsolidator(
        store=memory_store,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    session_summariser = SessionSummariser(
        pool=pool,
        embedder=embedder,
        openrouter_client=openrouter_client,
        settings=settings,
    )

    workflow_store = PostgresWorkflowStore(db_pool=pool)

    # WorkflowScheduler: executor is configured in PersonalPlugin.startup() once the
    # workflow graph is available. Must be built here so CalendarPlugin can reference
    # it during its startup().
    workflow_scheduler = WorkflowScheduler(
        workflow_store=workflow_store,
        enabled=settings.scheduler_enabled,
    )

    estimator = ComplexityEstimator()
    override_store = PostgresCapabilityOverrideStore(pool=pool)
    capability_gate = CapabilityGate(override_store=override_store)
    await capability_gate.load_persistent_overrides()

    # Build dep_map for plugin discovery. All types that plugin constructors
    # declare must be registered here.
    plugin_deps: dict[type, Any] = {
        asyncpg.Pool: pool,
        OpenRouterClient: openrouter_client,
        LLMClient: openrouter_client,
        Settings: settings,
        CoreSettings: core_settings,
        ProactiveNotifier: notifier,
        PushLogStore: push_log_store,
        PostgresMemoryStore: memory_store,
        WorkflowStore: workflow_store,
        WorkflowScheduler: workflow_scheduler,
        SentenceTransformer: embedder,
        BrowserClient: browser_client,
    }

    plugin_classes = _load_plugin_classes()
    integration_deps = build_integrations(plugin_classes, settings)
    plugin_deps.update(integration_deps)
    plugins = _instantiate_plugins(plugin_classes, plugin_deps)

    from ze_agents.progress.translations import ProgressTranslations

    locale: str = settings.config.get("locale", "en")
    en_layers = [p.locale_data("en") for p in plugins]
    target_layers = [p.locale_data(locale) for p in plugins] if locale != "en" else en_layers
    app_en = ProgressTranslations._load_file(settings.config_dir / "locales" / "en.yaml")
    app_locale = (
        ProgressTranslations._load_file(settings.config_dir / "locales" / f"{locale}.yaml")
        if locale != "en"
        else app_en
    )
    translations = ProgressTranslations.build(
        layers=target_layers + [app_locale],
        fallback_layers=en_layers + [app_en],
    )
    log.info("progress_translations_built", locale=locale)

    from ze_memory.policies import build_policy_registry

    memory_store.apply_policy_registry(build_policy_registry(plugins))

    from ze_core.checkpoint_serde import build_checkpoint_serde

    checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=build_checkpoint_serde(plugins))
    await checkpointer.setup()

    # Wire onboarding providers.
    onboarding_providers = [CoreOnboardingProvider()]
    for plugin in plugins:
        provider = plugin.onboarding()
        if provider is not None:
            onboarding_providers.append(provider)
            log.info(
                "onboarding_provider_registered",
                plugin=provider.plugin_name,
                priority=provider.priority,
            )
    onboarding_store = OnboardingStore(pool=pool)
    onboarding_persistence = OnboardingPersistence(
        memory_store=memory_store,
    )
    onboarding_coordinator = OnboardingCoordinator(
        providers=onboarding_providers,
        store=onboarding_store,
        persistence=onboarding_persistence,
    )
    reset_service = ResetService(pool=pool)

    # Each plugin declares what it contributes to the agent dep-map.
    # accumulated is passed so plugins can resolve cross-plugin deps (e.g.
    # GoalTitleProvider pointing at PersonalPlugin's goal_store).
    agent_deps: dict[type, Any] = dict(plugin_deps)
    for plugin in plugins:
        agent_deps.update(plugin.agent_deps(agent_deps))

    # Collect REST stores from all plugins — no per-plugin wiring needed in ZeContainer.
    plugin_stores: dict = {}
    for plugin in plugins:
        plugin_stores.update(plugin.rest_stores())

    signal_sources = collect_plugin_signal_sources(plugins)
    if signal_sources:
        log.info("signal_sources_collected", keys=list(signal_sources))

    bootstrap_agents(deps=agent_deps, plugins=plugins)

    router = EmbeddingRouter(
        embedder=embedder,
        openrouter_client=openrouter_client,
        routing_store=PostgresRoutingStore(pool),
        config=RouterConfig(),
        estimator=estimator,
    )
    component_hook = ComponentCollectionHook()
    register_hook(component_hook)
    log.info("component_collection_hook_registered")

    register_hook(ToolCallCapHook(max_tool_calls=settings.max_tool_calls_per_turn))
    log.info("tool_call_cap_hook_registered", max_tool_calls=settings.max_tool_calls_per_turn)

    graph = build_graph(checkpointer=checkpointer, plugins=plugins)

    from ze_data.portability.service import DataPortabilityService
    from ze_data.portability.assembler import bulk_insert
    from ze_data.domain import DataDomain

    def _mk_export(tbl: str):
        async def _export(p) -> list[dict]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(f"SELECT * FROM {tbl}")
                return [dict(r) for r in rows]
        return _export

    def _mk_delete(*tables: str):
        async def _delete(p) -> None:
            async with pool.acquire() as conn:
                for tbl in tables:
                    await conn.execute(f"DELETE FROM {tbl}")
        return _delete

    def _mk_import(tbl: str):
        async def _import(conn, rows: list[dict]) -> int:
            return await bulk_insert(conn, tbl, rows)
        return _import

    async def _export_checkpoints(p) -> list[dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM checkpoints")
            return [dict(r) for r in rows]

    async def _delete_checkpoints(p) -> None:
        async with pool.acquire() as conn:
            for tbl in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await conn.execute(f"DELETE FROM {tbl}")

    def _engine_domain(name: str, tbl: str) -> DataDomain:
        return DataDomain(name, _mk_export(tbl), _mk_delete(tbl), delete_order=10, importer=_mk_import(tbl))

    engine_domains: list[DataDomain] = [
        _engine_domain("telemetry.costs", "llm_cost_log"),
        _engine_domain("telemetry.anomalies", "accountability_anomalies"),
        _engine_domain("telemetry.capabilities", "capability_overrides"),
        _engine_domain("routing.log", "routing_log"),
        _engine_domain("messages.store", "messages"),
        _engine_domain("confirmations", "pending_confirmations"),
        _engine_domain("proactive.log", "push_log"),
        _engine_domain("sessions", "sessions"),
        DataDomain(
            "onboarding",
            _mk_export("onboarding_sessions"),
            _mk_delete("onboarding_steps", "onboarding_sessions", "onboarding_seeds"),
            delete_order=10,
            importer=_mk_import("onboarding_sessions"),
        ),
        DataDomain("graph.checkpoints", _export_checkpoints, _delete_checkpoints, delete_order=50),
    ]
    all_domains = engine_domains + [d for plugin in plugins for d in plugin.data_domains()]
    data_portability_service = DataPortabilityService(pool=pool, domains=all_domains)
    log.info("data_portability_service_ready", domains=len(all_domains))

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
        translations=translations,
        signal_sources=signal_sources,
        correlation_engine=correlation_engine,
        persona_store=persona_store,
        workflow_store=workflow_store,
        _plugin_stores=plugin_stores,
        workflow_scheduler=workflow_scheduler,
        proactive_scheduler=ProactiveScheduler(),
        browser_client=browser_client,
        push_notifier=push_notifier,
        message_store=message_store,
        session_store=session_store,
        connection_manager=connection_manager,
        component_hook=component_hook,
        confirmation_store=confirmation_store,
        onboarding_coordinator=onboarding_coordinator,
        reset_service=reset_service,
        plugins=plugins,
        _checkpointer=checkpointer,
        _push_log_store=push_log_store,
        data_portability_service=data_portability_service,
    )

    for plugin in plugins:
        try:
            await plugin.startup(container)
            log.info("plugin_started", plugin=type(plugin).__name__)
        except Exception as exc:
            log.error("plugin_startup_failed", plugin=type(plugin).__name__, error=str(exc))
            raise

    # Schedule cost reconciliation.
    cost_reconciler = CostReconciler(store=cost_store, openrouter_client=openrouter_client)
    workflow_scheduler.schedule_job(
        fn=cost_reconciler.run,
        cron="*/15 * * * *",
        job_id="cost_reconciliation",
    )
    log.info("cost_reconciliation_scheduled")

    # Schedule memory consolidation (contacts consolidation is registered in PersonalPlugin.startup).
    if settings.consolidation_enabled:
        nightly_cron = settings.consolidation_config.get("nightly_cron") or "0 2 * * *"
        container.proactive_scheduler.add_cron_job(
            fn=memory_consolidator.run,
            cron=nightly_cron,
            job_id="memory_consolidation",
        )
        log.info("consolidation_scheduled", cron=nightly_cron)

        from ze_memory.defaults import SESSION_SUMMARY_CHECK_INTERVAL_MINUTES
        _ss_cfg = (getattr(settings, "config", {}) or {}).get("memory", {}).get("session_summary", {})
        _ss_interval = int(_ss_cfg.get("check_interval_minutes", SESSION_SUMMARY_CHECK_INTERVAL_MINUTES))
        _ss_enabled = _ss_cfg.get("enabled", True)
        if _ss_enabled:
            container.proactive_scheduler.add_cron_job(
                fn=session_summariser.run,
                cron=f"*/{_ss_interval} * * * *",
                job_id=SessionSummariser.job_id,
            )
            log.info("session_summary_scheduled", interval_minutes=_ss_interval)

    # Wire correlation push job if configured.
    raw_cfg = getattr(settings, "config", {}) or {}
    _push_cfg = raw_cfg.get("correlation", {}).get("push", {})
    _push_schedule = _push_cfg.get("schedule", "0 */4 * * *")
    push_consumer = CorrelationPushConsumer(
        engine=correlation_engine,
        hypothesis_store=hypothesis_store,
        memory_store=memory_store,
        notifier=notifier,
        push_log=push_log_store,
        settings=settings,
        embedder=embedder,
    )
    correlation_job = CorrelationJob(push_consumer=push_consumer)
    container.proactive_scheduler.add_cron_job(
        fn=correlation_job.run,
        cron=_push_schedule,
        job_id=CorrelationJob.job_id,
    )
    log.info("correlation_push_job_scheduled", cron=_push_schedule)

    # Register plugin proactive jobs.
    for plugin in plugins:
        plugin.register_proactive_jobs(
            container.proactive_scheduler,
            core_settings,
            consolidation_enabled=settings.consolidation_enabled,
        )

    # Build channel registry from all plugins.
    all_channels = [ch for plugin in plugins for ch in plugin.channels()]
    _ = ChannelRegistry(channels=all_channels)

    await workflow_scheduler.start()
    await container.proactive_scheduler.start()

    return container
