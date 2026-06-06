from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.graph import StateGraph
    from ze_core.orchestration.base_agent import BaseAgent
    from ze_core.proactive.job import ProactiveJob


class ZePlugin(ABC):
    """Extension point for domain packages.

    Container-level hooks (agents, jobs, migrations) are wired by ZeContainer.
    Graph-level hooks (state_extensions, graph_nodes, graph_edges, configurable_services)
    are applied at graph build time so domain packages contribute nodes and state
    without touching ze_core internals.

    All methods have default no-op implementations — only override what you need.
    """

    # ── Container level ───────────────────────────────────────────────────────

    def agents(self) -> list[type[BaseAgent]]:
        return []

    def jobs(self) -> list[ProactiveJob]:
        return []

    def migrations_path(self) -> Path | None:
        return None

    # ── Graph level ───────────────────────────────────────────────────────────

    def state_extensions(self) -> type | None:
        """Return a TypedDict subclass whose fields are merged into AgentState.

        Applied at graph build time. Return None to add no extra fields.
        """
        return None

    def pre_route_node(self) -> Callable | None:
        """Return an async node to insert between preprocess and embed_route.

        Used to inject runtime routing context (e.g. active goal hints) into
        state before the embedding router runs. Return None to add no pre-route step.
        At most one plugin may provide a pre-route node.
        """
        return None

    def graph_nodes(self) -> dict[str, Callable]:
        """Return additional graph nodes keyed by node name."""
        return {}

    def graph_edges(self, builder: StateGraph) -> None:
        """Wire plugin nodes into the graph.

        Called after all base edges and plugin nodes have been added, before
        graph compilation.
        """

    def configurable_services(self) -> dict[str, Any]:
        """Return services to inject into config["configurable"] for every turn."""
        return {}

    def agent_module_paths(self) -> list[str]:
        """Fully-qualified module paths to import at bootstrap to trigger @agent registration.

        Modules are imported before ze/ agent discovery, so plugin agents are in the
        @agent registry when bootstrap resolves instances.
        """
        return []
