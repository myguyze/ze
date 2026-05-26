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
        await _dispose_pool(self.checkpointer_pool)
        await _dispose_pool(self.pool)
        log.info("container_closed")

    @classmethod
    async def from_config(
        cls,
        config_path: Path,
        deps: dict[type, Any] | None = None,
    ) -> "Container":
        config_path = Path(config_path)
        app_root = config_path.parent

        # 1. Load Settings
        from ze_core.settings import Settings

        settings = Settings.from_env(config_path)

        # 2. Create asyncpg pools
        import asyncpg  # type: ignore[import]

        pool = await asyncpg.create_pool(settings.database_url)
        checkpointer_pool = await asyncpg.create_pool(settings.database_url)

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

        internal_deps: dict[type, Any] = {
            Settings: settings,
            asyncpg.Pool: pool,
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

        router = EmbeddingRouter(embedder=embedder)

        # 10. Build CapabilityGate
        from ze_core.capability.gate import CapabilityGate

        capability_gate = CapabilityGate()

        # 11. Build MemoryStore
        from ze_core.memory.store import MemoryStore

        memory_store = MemoryStore(
            pool=pool,
            embedder=embedder,
            openrouter_client=openrouter_client,
            settings=settings,
        )

        # 12. Build MemoryConsolidator
        from ze_core.memory.consolidator import MemoryConsolidator

        memory_consolidator = MemoryConsolidator(
            pool=pool,
            embedder=embedder,
            openrouter_client=openrouter_client,
            settings=settings,
        )

        # 13. Build LangGraph checkpointer and compile graph
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore[import]
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # type: ignore[import]

        from ze_core.orchestration.graph import build_graph

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
    from ze_core.orchestration.registry import get_registered_agents
    from ze_core.orchestration.tool import registered_tools

    tool_reg = registered_tools()
    registered = get_registered_agents()

    for name, cls in registered.items():
        if not getattr(cls, "name", ""):
            raise AgentConfigError(f"{cls.__name__} must define a non-empty `name`")
        if not getattr(cls, "description", "").strip():
            raise AgentConfigError(
                f"Agent {name!r} must define a non-empty `description`"
            )
        for tool_name in getattr(cls, "tools", []):
            if tool_name not in tool_reg:
                raise AgentConfigError(
                    f"Agent {name!r} declares unknown tool {tool_name!r}"
                )
        capabilities = getattr(cls, "capabilities", {})
        for intent in getattr(cls, "intent_map", {}):
            if intent not in capabilities:
                raise AgentConfigError(
                    f"Agent {name!r} intent_map key {intent!r} not in capabilities"
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


async def _dispose_pool(pool: Any) -> None:
    try:
        await pool.close()
    except Exception as exc:
        log.warning("pool_close_failed", error=str(exc))
