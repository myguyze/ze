"""Test helper for building a CapabilityGate from synthetic agent classes."""

from __future__ import annotations

import ze_agents.registry as zc_registry
from ze_agents.bootstrap import reload_agent_modules
from ze_agents.types import Intent, Mode
from ze_core.capability.gate import CapabilityGate

from tests.support.agent_modules import ALL_AGENT_MODULE_PATHS


def make_gate(
    agents_config: dict,
    *,
    override_store=None,
) -> CapabilityGate:
    reload_agent_modules(ALL_AGENT_MODULE_PATHS)
    backup_registry = dict(zc_registry._registry)
    backup_instances = dict(zc_registry._instances)
    zc_registry._registry.clear()
    zc_registry._instances.clear()

    for name, cfg in agents_config.items():
        caps_raw = cfg.get("capabilities", {})
        intents = {intent: Intent(Mode(mode_str)) for intent, mode_str in caps_raw.items()}
        gate_cls = type(
            f"GateConfig_{name}",
            (),
            {
                "name": name,
                "description": str(cfg.get("description") or name),
                "enabled": cfg.get("enabled", True),
                "intents": intents,
                "model": cfg.get("model", "anthropic/claude-sonnet-4-5"),
                "model_simple": cfg.get("model_simple", ""),
                "tools": cfg.get("tools", []),
            },
        )
        zc_registry._registry[name] = gate_cls

    gate = CapabilityGate(override_store=override_store)

    def restore() -> None:
        zc_registry._registry.clear()
        zc_registry._registry.update(backup_registry)
        zc_registry._instances.clear()
        zc_registry._instances.update(backup_instances)
        if "research" not in zc_registry._registry:
            reload_agent_modules(ALL_AGENT_MODULE_PATHS)

    gate._restore_registry = restore  # type: ignore[attr-defined]
    return gate
