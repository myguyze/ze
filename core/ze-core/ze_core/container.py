from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_type_hints

from ze_agents.errors import AgentConfigError, RoutingError
from ze_agents.interface.types import RawInput
from ze_logging import get_logger
from ze_agents.types import AbortToken
from ze_core.conversation import make_graph_input

if TYPE_CHECKING:
    from ze_agents.interface.types import InvokeResult

log = get_logger(__name__)


@dataclass
class Container:
    settings: Any
    pool: Any
    checkpointer_pool: Any
    embedder: Any
    openrouter_client: Any
    router: Any
    capability_gate: Any
    memory_store: Any
    memory_consolidator: Any
    graph: Any
    interface: Any = None
    preprocessor: Any = None  # InputPreprocessor | None
    plugins: list = field(default_factory=list)  # list[ZePlugin]
    _abort_tokens: dict = field(default_factory=dict)  # thread_id → AbortToken
    _fact_extractor: Any = None    # ze_memory.extractor.gather_fact_proposals or None
    _event_extractor: Any = None   # ze_memory.extractor.gather_event_proposals or None
    _entity_extractor: Any = None  # ze_memory.extractor.gather_entity_proposals or None

    def _build_config(self, thread_id: str, **extra: Any) -> dict:
        """Build the LangGraph configurable dict for a conversation thread."""
        plugin_services: dict[str, Any] = {}
        for plugin in self.plugins:
            plugin_services.update(plugin.configurable_services())

        return {
            "configurable": {
                "thread_id": thread_id,
                "router": self.router,
                "openrouter_client": self.openrouter_client,
                "capability_gate": self.capability_gate,
                "memory_store": self.memory_store,
                "fact_extractor": self._fact_extractor,
                "event_extractor": self._event_extractor,
                "entity_extractor": self._entity_extractor,
                **plugin_services,
                **extra,
            }
        }

    async def invoke(
        self,
        prompt: str,
        thread_id: str,
        *,
        session_overrides: dict[str, str] | None = None,
        audio_data: bytes | None = None,
        audio_mime: str | None = None,
        image_data: bytes | None = None,
        image_mime: str | None = None,
        messages: list[dict] | None = None,
    ) -> "InvokeResult":
        """Run a full conversation turn, handling the confirmation loop.

        For **inline** confirmation: calls interface.confirm(), resumes the
        graph on approval, and delivers the final response via interface.send().

        For **async** confirmation: calls interface.send_confirmation() and
        returns InvokeResult(confirmation_pending=True). The caller must invoke
        Container.resume() once the user decision arrives.

        If no interface is configured, the graph is invoked once and
        final_response is returned directly without any delivery call.
        """
        from ze_agents.interface.types import ConfirmationRequest, InvokeResult, OutboundMessage

        graph_input = make_graph_input(
            RawInput(
                text=prompt,
                audio=audio_data,
                audio_mime=audio_mime,
                image=image_data,
                image_mime=image_mime,
            ),
            thread_id,
            session_overrides=session_overrides,
        )
        # Only overwrite the checkpointed history when the caller supplies one;
        # otherwise the prior turns persist and write_memory keeps appending.
        if messages is not None:
            graph_input["messages"] = messages
        abort_token = AbortToken()
        self._abort_tokens[thread_id] = abort_token
        config = self._build_config(thread_id, abort_token=abort_token)

        try:
            state = await self.graph.ainvoke(graph_input, config)

            if state.get("error"):
                return InvokeResult(session_id=thread_id, error=state["error"])

            if state.get("pending_confirmation"):
                agent_result = state.get("agent_result")
                draft = agent_result.response if agent_result is not None else ""
                request = ConfirmationRequest(
                    content=draft or "",
                    options=["Approve", "Cancel"],
                    timeout_seconds=getattr(self.settings, "confirm_timeout_seconds", None),
                )

                if self.interface is None:
                    return InvokeResult(session_id=thread_id, confirmation_pending=True)

                style = getattr(type(self.interface), "confirmation_style", None)

                if style == "async":
                    await self.interface.send_confirmation(request)
                    return InvokeResult(session_id=thread_id, confirmation_pending=True)

                # inline — block until user responds
                decision = await self.interface.confirm(request)
                if not decision.approved:
                    cancelled = decision.edited_content or draft or ""
                    return InvokeResult(session_id=thread_id, response=cancelled)

                # Resume the graph after approval
                state = await self.graph.ainvoke(None, config)

            response = state.get("final_response") or ""
            if self.interface and response:
                await self.interface.send(OutboundMessage(content=response))
            return InvokeResult(session_id=thread_id, response=response)
        finally:
            self._abort_tokens.pop(thread_id, None)

    async def abort_invocation(self, thread_id: str, reason: str | None = None) -> None:
        """Signal the agentic loop running under thread_id to stop cleanly.

        No-op if thread_id has no active invocation (already completed or never started).
        """
        token = self._abort_tokens.get(thread_id)
        if token is not None:
            token.abort(reason)

    async def abort_pending_checkpoint(self, config: dict) -> None:
        """Finalize a LangGraph checkpoint paused at await_confirmation.

        The graph compiles with interrupt_before=["await_confirmation"], so a
        deny or timeout leaves a checkpoint with next=["await_confirmation"].
        This advances past that node without executing the pending action, so
        the next turn starts from the entry node instead of the interrupted state.
        """
        try:
            state = await self.graph.aget_state(config)
            if not state or not state.next:
                return
            await self.graph.update_state(
                config,
                {"pending_confirmation": False, "agent_result": None, "agent_context": None},
                as_node="write_memory",
            )
            await self.graph.ainvoke(None, config)
        except Exception as exc:
            log.warning("abort_pending_checkpoint_failed", error=str(exc))

    async def invoke_raw(
        self,
        raw: RawInput,
        thread_id: str,
        *,
        session_overrides: dict[str, str] | None = None,
        messages: list[dict] | None = None,
    ) -> "InvokeResult":
        """Run a conversation turn from raw transport input.

        Audio and image bytes are passed directly into AgentState; the graph's
        ``preprocess`` node handles transcription and vision captioning via
        OpenRouterClient so no LLM calls are made here.
        """
        return await self.invoke(
            prompt=raw.text or "",
            thread_id=thread_id,
            session_overrides=session_overrides,
            audio_data=raw.audio,
            audio_mime=raw.audio_mime,
            image_data=raw.image,
            image_mime=raw.image_mime,
            messages=messages,
        )

    async def resume(self, thread_id: str) -> "InvokeResult":
        """Resume a graph that paused at await_confirmation (async style).

        Called by the transport callback handler after the user decision has
        been written into AgentState and the application is ready to continue.
        """
        from ze_agents.interface.types import InvokeResult, OutboundMessage

        config = self._build_config(thread_id)
        state = await self.graph.ainvoke(None, config)

        if state.get("error"):
            return InvokeResult(session_id=thread_id, error=state["error"])

        response = state.get("final_response") or ""
        if self.interface and response:
            await self.interface.send(OutboundMessage(content=response))
        return InvokeResult(session_id=thread_id, response=response)

    async def close(self) -> None:
        from ze_agents.registry import get_enabled_instances

        for instance in get_enabled_instances().values():
            try:
                await instance.shutdown()
            except Exception as exc:
                log.warning(
                    "agent_shutdown_failed",
                    agent=getattr(instance, "name", "?"),
                    error=str(exc),
                )

        await self.openrouter_client.aclose()
        aclose = getattr(self.memory_store, "aclose", None)
        if callable(aclose):
            import asyncio
            if asyncio.iscoroutinefunction(aclose):
                await aclose()
        await _dispose_pool(self.checkpointer_pool)
        await _dispose_pool(self.pool)
        log.info("container_closed")

    @classmethod
    async def from_config(
        cls,
        config_path: Path,
        deps: dict[type, Any] | None = None,
        interface: Any = None,
        plugins: list | None = None,
    ) -> "Container":
        config_path = Path(config_path)
        app_root = config_path.parent

        # 0. Validate interface early so misconfiguration fails fast
        if interface is not None:
            from ze_agents.interface.validation import validate_interface
            validate_interface(interface)

        # 1. Load Settings
        from ze_agents.settings import Settings

        settings = Settings.from_env(config_path)

        # 2. Create database pools / connections
        is_sqlite = settings.database_url.lower().startswith("sqlite")

        if is_sqlite:
            pool = None
            checkpointer_pool = None
        else:
            import asyncpg  # type: ignore[import]

            pool = await asyncpg.create_pool(settings.database_url)
            checkpointer_pool = await asyncpg.create_pool(settings.database_url)

            # 2a. Optionally apply pending migrations (ZC_AUTO_MIGRATE=true)
            if settings.auto_migrate:
                from ze_core.migrate import upgrade
                log.info("container_auto_migrate_start")
                upgrade(settings.database_url_sync)
                log.info("container_auto_migrate_done")

        # 3. Load embedder (sentence_transformers)
        from ze_core.embeddings import get_embedder

        _embedding_model = settings.config.get("models", {}).get("embedding")
        embedder = get_embedder(_embedding_model) if _embedding_model else get_embedder()
        from ze_core.nli import LocalNLIClient

        nli_client = LocalNLIClient()

        # 4. Build OpenRouterClient
        from ze_core.openrouter.client import OpenRouterClient

        openrouter_client = OpenRouterClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            logger=log,
        )

        # 5. Discover agent modules
        package = _infer_package(app_root)
        _discover_agents(app_root, package)

        # 6. Validate registered agent classes
        _validate_registry(settings)

        # 7. Instantiate enabled agents
        from ze_agents.registry import get_enabled_agents

        from ze_core.db import DBPool

        internal_deps: dict[type, Any] = {
            Settings: settings,
            DBPool: pool,
            OpenRouterClient: openrouter_client,
        }
        merged = {**internal_deps, **(deps or {})}
        instances = _instantiate_agents(get_enabled_agents(), merged)

        # 8. Call startup() on all instances concurrently
        await asyncio.gather(
            *[inst.startup() for inst in instances.values()],
            return_exceptions=True,
        )

        # 9. Build EmbeddingRouter
        from ze_agents.defaults import MODEL_ROUTER_FALLBACK
        from ze_agents.model_resolution import resolve_model
        from ze_core.routing.router import EmbeddingRouter
        from ze_core.routing.types import RouterConfig

        _validate_model_config(settings)

        routing_cfg = settings.config.get("routing", {})
        _defaults = RouterConfig()
        router_config = RouterConfig(
            threshold=routing_cfg.get("threshold", _defaults.threshold),
            gap_threshold=routing_cfg.get("gap_threshold", _defaults.gap_threshold),
            fallback_model=resolve_model("router_fallback", MODEL_ROUTER_FALLBACK, settings.config),
        )
        from ze_core.routing.store import PostgresRoutingStore

        routing_store = PostgresRoutingStore(pool) if not is_sqlite else None
        router = EmbeddingRouter(
            embedder=embedder,
            openrouter_client=openrouter_client,
            routing_store=routing_store,
            config=router_config,
            app_config=settings.config,
        )

        # 10. Build CapabilityGate
        from ze_core.capability.gate import CapabilityGate

        capability_gate = CapabilityGate()

        # 11. Build MemoryStore and MemoryConsolidator
        from ze_memory.extractor import gather_entity_proposals, gather_event_proposals, gather_fact_proposals
        from ze_memory.retriever import PostgresMemoryStore

        if is_sqlite:
            memory_store = PostgresMemoryStore(
                pool=pool,
                embedder=embedder,
                openrouter_client=openrouter_client,
                settings=settings,
                nli_client=nli_client,
            )
            memory_consolidator = None
        else:
            from ze_memory.consolidation_store import PostgresConsolidationStore
            from ze_memory.consolidator import MemoryConsolidator

            memory_store = PostgresMemoryStore(
                pool=pool,
                embedder=embedder,
                openrouter_client=openrouter_client,
                settings=settings,
                nli_client=nli_client,
            )
            memory_consolidator = MemoryConsolidator(
                store=PostgresConsolidationStore(pool),
                embedder=embedder,
                openrouter_client=openrouter_client,
                settings=settings,
                nli_client=nli_client,
            )

        # 12. Build LangGraph checkpointer and compile graph
        from ze_core.orchestration.graph import build_graph

        resolved_plugins = plugins or []
        if is_sqlite:
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import]

            checkpointer = MemorySaver()
        else:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import]
            from ze_core.checkpoint_serde import build_checkpoint_serde

            serde = build_checkpoint_serde(resolved_plugins)
            checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=serde)
            await checkpointer.setup()

        graph = build_graph(checkpointer, plugins=resolved_plugins)

        log.info("container_ready", agents=list(instances.keys()))
        return cls(
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
            plugins=resolved_plugins,
            _fact_extractor=gather_fact_proposals,
            _event_extractor=gather_event_proposals,
            _entity_extractor=gather_entity_proposals,
        )


# ── private helpers ───────────────────────────────────────────────────────────

def _discover_agents(app_root: Path, package: str) -> None:
    agents_dir = app_root / "agents"
    if not agents_dir.exists():
        raise AgentConfigError(f"agents/ directory not found at {agents_dir}")

    for subdir in sorted(agents_dir.iterdir()):
        if subdir.is_dir() and (subdir / "agent.py").exists():
            module_path = f"{package}.agents.{subdir.name}.agent"
            importlib.import_module(module_path)


def _validate_registry(settings: Any) -> None:
    """Validate tool names against the tool registry (name/description/capabilities
    are already validated by @agent at decoration time)."""
    from ze_agents.registry import get_registered_agents
    from ze_agents.tool import registered_tools

    tool_reg = registered_tools()
    registered = get_registered_agents()

    for name, cls in registered.items():
        for tool_name in getattr(cls, "tools", []):
            if tool_name not in tool_reg:
                raise AgentConfigError(
                    f"Agent {name!r} declares unknown tool {tool_name!r}"
                )

    enabled = {n: c for n, c in registered.items() if getattr(c, "enabled", True)}
    if not enabled:
        raise RoutingError("No enabled agents found after discovery")


def _validate_model_config(settings: Any) -> None:
    """Fail fast at startup if `models.default`/`models.overrides` are malformed."""
    from ze_agents.model_resolution import KNOWN_STEP_KEYS, validate_model_config
    from ze_agents.registry import get_enabled_agents

    known_model_keys = frozenset(get_enabled_agents().keys()) | KNOWN_STEP_KEYS
    validate_model_config(settings.config, known_model_keys)


def _resolve(cls: type, deps: dict[type, Any]) -> Any:
    try:
        hints = get_type_hints(cls.__init__)
    except Exception:
        hints = {}

    sig = inspect.signature(cls.__init__)
    kwargs: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        annotation = hints.get(param_name)
        if annotation is None:
            raise AgentConfigError(
                f"{cls.__name__}.__init__ parameter {param_name!r} has no type annotation"
            )
        if annotation not in deps:
            raise AgentConfigError(
                f"No dependency registered for {annotation!r}"
                f" (required by {cls.__name__})."
                " Add it to deps before calling from_config()."
            )
        kwargs[param_name] = deps[annotation]

    return cls(**kwargs)


def _instantiate_agents(
    registered: dict[str, Any],
    deps: dict[type, Any],
) -> dict[str, Any]:
    from ze_agents.registry import register_instance

    instances: dict[str, Any] = {}
    for name, cls in registered.items():
        if not getattr(cls, "enabled", True):
            continue
        instance = _resolve(cls, deps)
        register_instance(name, instance)
        instances[name] = instance
    return instances


def _infer_package(app_root: Path) -> str:
    resolved = app_root.resolve()
    for entry in sys.path:
        if not entry:
            continue
        try:
            rel = resolved.relative_to(Path(entry).resolve())
            if rel.parts:
                return rel.parts[0]
        except ValueError:
            continue
    return app_root.name


def _sqlite_db_path(url: str) -> str:
    """Extract the file path from a sqlite:// URL.

    sqlite:///./app.db   -> ./app.db
    sqlite:////abs/p.db  -> /abs/p.db
    sqlite:///:memory:   -> :memory:
    """
    # Strip the sqlite:// or sqlite:/// prefix
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    if url.startswith("sqlite://"):
        return url[len("sqlite://"):]
    return url


async def _dispose_pool(pool: Any) -> None:
    if pool is None:
        return
    try:
        await pool.close()
    except Exception as exc:
        log.warning("pool_close_failed", error=str(exc))
