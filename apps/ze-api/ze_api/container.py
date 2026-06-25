from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from sentence_transformers import SentenceTransformer

from ze_agents.nli import NLIClient
from ze_agents.bootstrap import bootstrap_agents
from ze_agents.interface.types import RawInput
from ze_agents.interface.validation import validate_interface
from ze_agents.settings import Settings as CoreSettings
from ze_automation.bootstrap import (
    automation_data_domains,
    build_automation_stack,
    configure_workflow_executor,
    import_agent_modules as import_automation_agents,
)
from ze_browser import BrowserClient
from ze_components.hook import ComponentCollectionHook
from ze_core.nli import LocalNLIClient
from ze_core.bootstrap import (
    build_checkpointer,
    build_engine_stack,
    build_router,
    engine_data_domains,
    register_engine_jobs,
    register_harness_hooks,
)
from ze_core.container import Container as CoreContainer
from ze_core.conversation import TurnResult, invoke_raw_turn, resume_turn
from ze_core.conversation.confirmations import PendingConfirmationStore
from ze_core.conversation.messages import PostgresMessageStore
from ze_core.conversation.sessions import PostgresSessionStore
from ze_core.orchestration.graph import build_graph
from ze_correlation.bootstrap import build_correlation_stack
from ze_data.portability.service import DataPortabilityService
from ze_ingestion.bootstrap import build_ingestion_stack, import_agent_modules as import_ingestion_agents
from ze_memory.policies import build_policy_registry
from ze_notifications.ntfy import NtfyConfig, NtfyNotifier
from ze_onboarding import (
    CoreOnboardingProvider,
    OnboardingCoordinator,
    PostgresOnboardingPersistence as OnboardingPersistence,
    PostgresOnboardingStore as OnboardingStore,
    ResetService,
)
from ze_personal.persona.postgres import PostgresPersonaStore
from ze_plugin.bootstrap import discover_and_instantiate_plugins
from ze_plugin.channels.registry import ChannelRegistry
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_proactive.scheduler import ProactiveScheduler
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.compose import register_all_proactive_jobs
from ze_api.db import create_checkpointer_pool, create_pool
from ze_api.interface.native import NativeAppInterface
from ze_logging import get_logger
from ze_api.settings import Settings, get_settings
import ze_components.tools  # noqa: F401 — registers all render tools at import time
import ze_agents.nli_tools  # noqa: F401 — registers shared NLI tools at import time

log = get_logger(__name__)


@dataclass(kw_only=True)
class ZeContainer(CoreContainer):
    """Ze application container — ze-core graph stack plus WebSocket, proactive, workflow."""

    translations: Any
    signal_sources: dict
    correlation_engine: Any | None
    persona_store: Any
    workflow_store: Any
    _plugin_stores: dict
    workflow_scheduler: Any
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
    _checkpointer: Any
    _push_log_store: PushLogStore
    data_portability_service: DataPortabilityService
    ingestion_pipeline: Any
    dream_store: Any

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
    pool = await create_pool(settings)
    checkpointer_pool = await create_checkpointer_pool(settings)

    shared = await build_engine_stack(pool, checkpointer_pool, settings)
    automation = build_automation_stack(shared, settings)
    correlation = build_correlation_stack(shared, settings)
    shared.dep_map.update(automation.deps)

    browser_client = BrowserClient(
        base_url=settings.browser_service_url,
        timeout=settings.browser_timeout_seconds,
    )

    push_notifier: NtfyNotifier | None = None
    if settings.ntfy_topic:
        ntfy_config = NtfyConfig(
            base_url=settings.ntfy_base_url,
            topic=settings.ntfy_topic,
            token=settings.ntfy_token or None,
        )
        ntfy_session = aiohttp.ClientSession()
        push_notifier = NtfyNotifier(config=ntfy_config, session=ntfy_session)
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

    core_settings: CoreSettings = shared.core_settings
    dep_map = dict(shared.dep_map)
    dep_map.update({
        Settings: settings,
        CoreSettings: core_settings,
        ProactiveNotifier: notifier,
        PushLogStore: push_log_store,
        SentenceTransformer: shared.embedder,
        NLIClient: shared.nli_client,
        LocalNLIClient: shared.nli_client,
        BrowserClient: browser_client,
    })

    plugins = discover_and_instantiate_plugins(dep_map, settings)
    ingestion = build_ingestion_stack(
        shared,
        settings,
        plugins,
        browser_client=browser_client,
    )

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

    shared.memory_store.apply_policy_registry(build_policy_registry(plugins))
    checkpointer = await build_checkpointer(checkpointer_pool, plugins)

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
    onboarding_coordinator = OnboardingCoordinator(
        providers=onboarding_providers,
        store=OnboardingStore(pool=pool),
        persistence=OnboardingPersistence(memory_store=shared.memory_store),
    )

    agent_deps: dict[type, Any] = dict(dep_map)
    for plugin in plugins:
        agent_deps.update(plugin.agent_deps(agent_deps))

    plugin_stores: dict = {}
    for plugin in plugins:
        plugin_stores.update(plugin.rest_stores())

    signal_sources = collect_plugin_signal_sources(plugins)
    if signal_sources:
        log.info("signal_sources_collected", keys=list(signal_sources))

    import_automation_agents()
    import_ingestion_agents()
    bootstrap_agents(deps=agent_deps, plugins=plugins)

    router = build_router(shared)
    component_hook = register_harness_hooks(settings)
    graph = build_graph(checkpointer=checkpointer, plugins=plugins)

    all_domains = (
        engine_data_domains(pool)
        + automation_data_domains(pool)
        + [d for plugin in plugins for d in plugin.data_domains()]
    )
    data_portability_service = DataPortabilityService(pool=pool, domains=all_domains)
    log.info("data_portability_service_ready", domains=len(all_domains))

    container = ZeContainer(
        settings=settings,
        pool=pool,
        checkpointer_pool=checkpointer_pool,
        embedder=shared.embedder,
        openrouter_client=shared.openrouter_client,
        router=router,
        capability_gate=shared.capability_gate,
        memory_store=shared.memory_store,
        memory_consolidator=shared.memory_consolidator,
        graph=graph,
        interface=interface,
        translations=translations,
        signal_sources=signal_sources,
        correlation_engine=correlation.correlation_engine,
        persona_store=persona_store,
        workflow_store=automation.workflow_store,
        _plugin_stores=plugin_stores,
        workflow_scheduler=automation.workflow_scheduler,
        proactive_scheduler=ProactiveScheduler(),
        browser_client=browser_client,
        push_notifier=push_notifier,
        message_store=message_store,
        session_store=session_store,
        connection_manager=connection_manager,
        component_hook=component_hook,
        confirmation_store=confirmation_store,
        onboarding_coordinator=onboarding_coordinator,
        reset_service=ResetService(pool=pool),
        plugins=plugins,
        _checkpointer=checkpointer,
        _push_log_store=push_log_store,
        data_portability_service=data_portability_service,
        ingestion_pipeline=ingestion.pipeline,
    )

    for plugin in plugins:
        try:
            await plugin.startup(container)
            log.info("plugin_started", plugin=type(plugin).__name__)
        except Exception as exc:
            log.error("plugin_startup_failed", plugin=type(plugin).__name__, error=str(exc))
            raise

    from ze_personal.graph.workflow import build_workflow_graph

    await configure_workflow_executor(
        automation,
        shared,
        plugins,
        settings=settings,
        notifier=notifier,
        push_log_store=push_log_store,
        checkpointer=checkpointer,
        router=router,
        persona_store=persona_store,
        workflow_graph_builder=build_workflow_graph,
    )

    from ze_memory.dream.store import PostgresDreamStore
    from ze_memory.dream.job import DreamJob

    dream_store = PostgresDreamStore(pool=pool)
    dream_job = DreamJob(
        pool=pool,
        embedder=shared.embedder,
        consolidator=shared.memory_consolidator,
        dream_store=dream_store,
        client=shared.openrouter_client,
        nli_client=shared.nli_client,
        settings=settings,
        notifier=notifier,
    )

    container.dream_store = dream_store

    register_all_proactive_jobs(
        container.proactive_scheduler,
        settings=settings,
        core_settings=core_settings,
        automation=automation,
        correlation=correlation,
        shared=shared,
        plugins=plugins,
        notifier=notifier,
        push_log_store=push_log_store,
        dream_job=dream_job,
    )

    _ = ChannelRegistry(channels=[ch for plugin in plugins for ch in plugin.channels()])

    await automation.workflow_scheduler.start()
    await container.proactive_scheduler.start()

    return container
