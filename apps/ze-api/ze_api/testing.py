"""Test helpers for building a CapabilityGate from @agent class metadata."""

from __future__ import annotations

from ze_core.capability.gate import CapabilityGate
from ze_core.capability.types import Mode
from ze_core.orchestration import registry as zc_registry


def make_gate(
    agents_config: dict,
    *,
    override_store=None,
) -> CapabilityGate:
    """Build a gate backed by synthetic agent classes for the given config.

    Saves and restores the live agent registry so other tests are not affected.
    Call ``gate._restore_registry()`` in fixture teardown (see capability conftest).
    """
    from ze_api.bootstrap import reload_agent_modules

    reload_agent_modules()
    backup_registry = dict(zc_registry._registry)
    backup_instances = dict(zc_registry._instances)
    zc_registry._registry.clear()
    zc_registry._instances.clear()

    for name, cfg in agents_config.items():
        caps_raw = cfg.get("capabilities", {})
        capabilities = {intent: Mode(mode_str) for intent, mode_str in caps_raw.items()}
        gate_cls = type(
            f"GateConfig_{name}",
            (),
            {
                "name": name,
                "description": str(cfg.get("description") or name),
                "enabled": cfg.get("enabled", True),
                "capabilities": capabilities,
                "intent_map": cfg.get("intent_map", {}),
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
            reload_agent_modules()

    gate._restore_registry = restore  # type: ignore[attr-defined]
    return gate
