from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph import StateGraph
    from ze_agents.base_agent import BaseAgent
    from ze_onboarding import OnboardingProvider

# Auto-populated by ZePlugin.__init_subclass__ when plugin modules are imported.
_registry: list[type["ZePlugin"]] = []


def get_plugin_registry() -> list[type["ZePlugin"]]:
    return list(_registry)


class ZePlugin(ABC):
    """Extension point for domain packages.

    Container-level hooks (agents, jobs, migrations) are wired by ZeContainer.
    Graph-level hooks (state_extensions, graph_nodes, graph_edges, configurable_services)
    are applied at graph build time so domain packages contribute nodes and state
    without touching ze_core internals.

    All methods have default no-op implementations — only override what you need.
    """

    # Class-level: names of other ZePlugin subclasses this plugin depends on.
    # bootstrap.py topologically sorts plugins by this before instantiation and startup.
    depends_on: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        _registry.append(cls)

    # ── Container level ───────────────────────────────────────────────────────

    def agents(self) -> list[type[BaseAgent]]:
        return []

    def jobs(self) -> list[Any]:
        return []

    def onboarding(self) -> OnboardingProvider | None:
        """Return this plugin's onboarding provider, if it participates in setup."""
        return None

    @classmethod
    def migrations_path(cls) -> Path | None:
        """Return the path to this plugin's Alembic versions directory, or None."""
        return None

    # ── Graph level ───────────────────────────────────────────────────────────

    def state_extensions(self) -> type | None:
        """Return a TypedDict subclass whose fields are merged into AgentState."""
        return None

    def pre_route_node(self) -> Callable | None:
        """Return an async node to insert between preprocess and embed_route."""
        return None

    def graph_nodes(self) -> dict[str, Callable]:
        """Return additional graph nodes keyed by node name."""
        return {}

    def graph_edges(self, builder: StateGraph) -> None:
        """Wire plugin nodes into the graph."""

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self, container: Any) -> None:
        """Called once during app startup after the container is fully built."""

    async def shutdown(self) -> None:
        """Called once during app shutdown, in reverse startup order."""

    # ── Graph level ───────────────────────────────────────────────────────────

    def configurable_services(self) -> dict[str, Any]:
        """Return services to inject into config["configurable"] for every turn."""
        return {}

    def agent_module_paths(self) -> list[str]:
        """Fully-qualified module paths to import at bootstrap to trigger @agent registration."""
        return []

    def agent_deps(self, accumulated: dict[type, Any]) -> dict[type, Any]:
        """Return types this plugin contributes to the agent dep-map.

        ``accumulated`` holds deps registered so far (shared infra + earlier plugins),
        allowing cross-plugin wiring (e.g. a type alias that resolves to another
        plugin's service).
        """
        return {}

    def channels(self) -> list[Any]:
        """Return communication channel instances this plugin provides."""
        return []

    def rest_stores(self) -> dict[str, Any]:
        """Return named stores this plugin exposes to REST routes.

        Keys are stable string identifiers (e.g. ``"goal_store"``).
        ZeContainer collects these into ``_plugin_stores`` so routes can access them
        without ZeContainer needing per-plugin typed fields.
        """
        return {}

    def register_proactive_jobs(
        self,
        scheduler: Any,
        settings: Any,
        *,
        consolidation_enabled: bool = True,
    ) -> None:
        """Register plugin cron jobs on the proactive scheduler."""
