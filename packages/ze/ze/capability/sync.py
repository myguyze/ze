"""Sync Ze YAML agent capabilities into ze-core's registry for CapabilityGate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ze_core.capability.types import Mode

if TYPE_CHECKING:
    from ze.settings import Settings


def sync_gate_registry(settings: Settings) -> None:
    """Register lightweight agent stubs in ze-core so the gate reads YAML modes.

    Ze agent classes remain in ``ze.agents.registry`` for execution. This only
    mirrors capability metadata until Phase 7 moves modes onto ``@agent`` classes.
    """
    from ze.agents.registry import _registry as ze_registry
    from ze_core.orchestration import registry as zc_registry

    for name in ze_registry:
        agent_cfg = settings.agent_configs.get(name, {})
        caps_raw = agent_cfg.get("capabilities", {})
        capabilities: dict[str, Mode] = {}
        for intent, mode_str in caps_raw.items():
            try:
                capabilities[intent] = Mode(mode_str)
            except ValueError:
                continue

        gate_cls = type(
            f"GateConfig_{name}",
            (),
            {
                "name": name,
                "description": str(agent_cfg.get("description") or name),
                "enabled": agent_cfg.get("enabled", True),
                "capabilities": capabilities,
                "intent_map": agent_cfg.get("intent_map", {}),
                "model": agent_cfg.get("model", "anthropic/claude-sonnet-4-5"),
                "model_simple": agent_cfg.get("model_simple", ""),
                "tools": [],
            },
        )
        zc_registry._registry[name] = gate_cls
