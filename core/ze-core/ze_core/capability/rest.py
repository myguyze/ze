from __future__ import annotations

from ze_agents.registry import get_registered_agents
from ze_agents.types import Mode
from ze_core.capability.gate import CapabilityGate


def effective_capabilities(gate: CapabilityGate) -> dict[str, dict]:
    cache = gate._persistent_cache or {}
    result: dict[str, dict] = {}
    for name, cls in get_registered_agents().items():
        if not getattr(cls, "enabled", True):
            continue
        caps = {intent: v.mode.value for intent, v in getattr(cls, "intents", {}).items()}
        for (a, intent), mode in cache.items():
            if a == name:
                caps[intent] = mode.value
        result[name] = {"enabled": getattr(cls, "enabled", True), **caps}
    return result


async def update_capability(
    gate: CapabilityGate,
    agent: str,
    intent: str,
    mode_value: str,
) -> dict[str, dict]:
    cls = get_registered_agents()[agent]
    mode = Mode(mode_value)
    await gate.set_permanent(agent, intent, mode)
    effective = effective_capabilities(gate)
    return {agent: effective[agent]}
