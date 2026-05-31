from __future__ import annotations

from typing import Any

from ze_core.plugin import ZePlugin


class PersonalPlugin(ZePlugin):
    """Domain plugin that wires the personal-assistant layer into ze_core graphs.

    Contributes:
    - identity_builder: builds the persona/memory context block injected into agent
      system prompts (via AgentContext.extensions).
    - memory_hooks: post-write callables; currently runs contact proposal extraction
      after every memory write.
    """

    def configurable_services(self) -> dict[str, Any]:
        from ze_personal.persona.identity import build_identity_block
        from ze_personal.graph.memory_hooks import contact_proposal_hook
        return {
            "identity_builder": build_identity_block,
            "memory_hooks": [contact_proposal_hook],
        }

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_personal.agents.goals.agent",
            "ze_personal.agents.workflow.agent",
        ]
