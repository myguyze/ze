from __future__ import annotations

from typing import Any, Callable

from ze_core.plugin import ZePlugin


class PersonalPlugin(ZePlugin):
    """Domain plugin that wires the personal-assistant layer into ze_core graphs.

    Contributes:
    - identity_builder: builds the persona/memory context block injected into agent
      system prompts (via AgentContext.extensions).
    - memory_hooks: post-write callables; currently runs contact proposal extraction
      after every memory write.
    - inject_goal_routing_context: pre-route node that enriches routing state with
      active goal context so goal-related messages route correctly.
    """

    def configurable_services(self) -> dict[str, Any]:
        from ze_personal.persona.identity import build_identity_block
        from ze_personal.graph.memory_hooks import contact_proposal_hook
        return {
            "identity_builder": build_identity_block,
            "memory_hooks": [contact_proposal_hook],
        }

    def pre_route_node(self) -> Callable | None:
        from ze_personal.graph.routing_context import inject_goal_routing_context
        return inject_goal_routing_context

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_personal.agents.goals.agent",
            "ze_personal.agents.workflow.agent",
        ]
