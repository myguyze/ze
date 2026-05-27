from __future__ import annotations

import asyncio
import importlib
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_type_hints

from ze_core.errors import AgentConfigError, RoutingError
from ze_core.logging import get_logger

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

    def _build_config(self, session_id: str, **extra: Any) -> dict:
        """Build the LangGraph configurable dict for a session."""
        return {
            "configurable": {
                "thread_id": session_id,
                "router": self.router,
                "openrouter_client": self.openrouter_client,
                "capability_gate": self.capability_gate,
                "memory_store": self.memory_store,
                **extra,
            }
        }

    async def invoke(
        self,
        prompt: str,
        session_id: str,
        *,
        session_overrides: dict[str, str] | None = None,
        input_modality: str = "text",
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
        from ze_core.interface.types import ConfirmationRequest, InvokeResult, OutboundMessage

        graph_input = {
            "prompt": prompt,
            "session_id": session_id,
            "session_overrides": session_overrides or {},
            "input_modality": input_modality,
            "image_data": image_data,
            "image_mime": image_mime,
            "image_caption": None,
            "messages": messages or [],
            "envelope": None,
            "memory_context": None,
            "agent_context": None,
            "gate_decision": None,
            "agent_result": None,
            "subtask_results": [],
            "pending_confirmation": False,
            "last_active_at": None,
            "final_response": None,
            "error": None,
        }
        config = self._build_config(session_id)

        state = await self.graph.ainvoke(graph_input, config)

        if state.get("error"):
            return InvokeResult(session_id=session_id, error=state["error"])

        if state.get("pending_confirmation"):
            agent_result = state.get("agent_result")
            draft = agent_result.response if agent_result is not None else ""
            request = ConfirmationRequest(
                content=draft or "",
                options=["Approve", "Cancel"],
                timeout_seconds=getattr(self.settings, "confirm_timeout_seconds", None),
            )

            if self.interface is None:
                return InvokeResult(session_id=session_id, confirmation_pending=True)

            style = getattr(type(self.interface), "confirmation_style", None)

            if style == "async":
                await self.interface.send_confirmation(request)
                return InvokeResult(session_id=session_id, confirmation_pending=True)

            # inline — block until user responds
            decision = await self.interface.confirm(request)
            if not decision.approved:
                cancelled = decision.edited_content or draft or ""
                return InvokeResult(session_id=session_id, response=cancelled)

            # Resume the graph after approval
            state = await self.graph.ainvoke(None, config)

        response = state.get("final_response") or ""
        if self.interface and response:
            await self.interface.send(OutboundMessage(content=response))
        return InvokeResult(session_id=session_id, response=response)

    async def resume(self, session_id: str) -> "InvokeResult":
        """Resume a graph that paused at await_confirmation (async style).

        Called by the transport callback handler after the user decision has
        been written into AgentState and the application is ready to continue.
        """
        from ze_core.interface.types import InvokeResult, OutboundMessage

        config = self._build_config(session_id)
        state = await self.graph.ainvoke(None, config)

        if state.get("error"):
            return InvokeResult(session_id=session_id, error=state["error"])

        response = state.get("final_response") or ""
        if self.interface and response:
            await self.interface.send(OutboundMessage(content=response))
        return InvokeResult(session_id=session_id, response=response)

    async def close(self) -> None:
        from ze_core.orchestration.registry import get_enabled_instances

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
    ) -> "Container":
        config_path = Path(config_path)
        app_root = config_path.parent

        # 0. Validate interface early so misconfiguration fails fast
        if interface is not None:
            from ze_core.interface.validation import validate_interface
            validate_interface(interface)

        # 1. Load Settings
        from ze_core.settings import Settings

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
        from sentence_transformers import SentenceTransformer  # type: ignore[import]

        embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # 4. Build OpenRouterClient
        from ze_core.openrouter.client import OpenRouterClient

        openrouter_client = OpenRouterClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )

        # 5. Discover agent modules
        package = _infer_package(app_root)
        _discover_agents(app_root, package)

        # 6. Validate registered agent classes
        _validate_registry(settings)

        # 7. Instantiate enabled agents
        from ze_core.orchestration.registry import get_enabled_agents

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
        from ze_core.routing.router import EmbeddingRouter
        from ze_core.routing.types import RouterConfig

        routing_cfg = settings.config.get("routing", {})
        _defaults = RouterConfig()
        router_config = RouterConfig(
            threshold=routing_cfg.get("threshold", _defaults.threshold),
            gap_threshold=routing_cfg.get("gap_threshold", _defaults.gap_threshold),
            fallback_model=routing_cfg.get("fallback_model", _defaults.fallback_model),
        )
        from ze_core.routing.store import PostgresRoutingStore

        routing_store = PostgresRoutingStore(pool) if not is_sqlite else None
        router = EmbeddingRouter(
            embedder=embedder,
            openrouter_client=openrouter_client,
            routing_store=routing_store,
            config=router_config,
        )

        # 10. Build CapabilityGate
        from ze_core.capability.gate import CapabilityGate

        capability_gate = CapabilityGate()

        # 11. Build MemoryStore and MemoryConsolidator
        if is_sqlite:
            from ze_core.memory.sqlite import SQLiteMemoryStore

            db_path = _sqlite_db_path(settings.database_url)
            memory_store = SQLiteMemoryStore(
                db_path=db_path,
                embedder=embedder,
                openrouter_client=openrouter_client,
                settings=settings,
            )
            await memory_store.setup()
            memory_consolidator = None  # consolidation not supported for SQLite yet
        else:
            from ze_core.memory.consolidator import MemoryConsolidator
            from ze_core.memory.postgres import PostgresMemoryStore

            memory_store = PostgresMemoryStore(
                pool=pool,
                embedder=embedder,
                openrouter_client=openrouter_client,
                settings=settings,
            )
            memory_consolidator = MemoryConsolidator(
                store=memory_store,
                embedder=embedder,
                openrouter_client=openrouter_client,
                settings=settings,
            )

        # 12. Build LangGraph checkpointer and compile graph
        from ze_core.orchestration.graph import build_graph

        if is_sqlite:
            from langgraph.checkpoint.memory import MemorySaver  # type: ignore[import]

            checkpointer = MemorySaver()
        else:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import]
            from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # type: ignore[import]

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
                ]
            )
            checkpointer = AsyncPostgresSaver(checkpointer_pool, serde=serde)
            await checkpointer.setup()

        graph = build_graph(checkpointer)

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
    from ze_core.orchestration.registry import get_registered_agents
    from ze_core.orchestration.tool import registered_tools

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
    from ze_core.orchestration.registry import register_instance

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
