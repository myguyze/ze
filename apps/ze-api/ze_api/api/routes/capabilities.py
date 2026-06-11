from fastapi import APIRouter, Depends, HTTPException

from ze_api.api.dependencies import get_capability_gate, get_settings
from ze_api.api.openapi import OPENAPI_RESPONSES_422
from ze_api.api.schemas import (
    AgentCapabilityConfig,
    CapabilitiesResponse,
    CapabilityModeUpdate,
    UpdateCapabilityResponse,
)
from ze_core.capability.gate import CapabilityGate
from ze_core.capability.types import Mode
from ze_api.settings import Settings
from ze_core.orchestration.registry import get_registered_agents

router = APIRouter(tags=["capabilities"])


def _effective_capabilities(
    gate: CapabilityGate,
) -> dict[str, AgentCapabilityConfig]:
    """Merge class-level defaults with DB-backed persistent overrides."""
    cache = gate._persistent_cache or {}
    result: dict[str, AgentCapabilityConfig] = {}

    for name, cls in get_registered_agents().items():
        if not getattr(cls, "enabled", True):
            continue
        caps = {intent: mode.value for intent, mode in getattr(cls, "capabilities", {}).items()}
        for (a, intent), mode in cache.items():
            if a == name:
                caps[intent] = mode.value
        result[name] = AgentCapabilityConfig.model_validate(
            {"enabled": getattr(cls, "enabled", True), **caps},
        )
    return result


@router.get(
    "",
    response_model=CapabilitiesResponse,
    summary="List capability modes",
    description=(
        "Return effective capability modes per agent (class defaults merged with "
        "any persistent DB overrides)."
    ),
)
def list_capabilities(
    gate: CapabilityGate = Depends(get_capability_gate),
) -> CapabilitiesResponse:
    return CapabilitiesResponse(_effective_capabilities(gate))


@router.put(
    "/{agent}/{intent}",
    response_model=UpdateCapabilityResponse,
    summary="Update capability mode",
    description=(
        "Set the permission mode for an agent intent. The change is persisted in "
        "the database and takes precedence over class defaults until cleared."
    ),
    responses=OPENAPI_RESPONSES_422,
)
async def update_capability(
    agent: str,
    intent: str,
    body: CapabilityModeUpdate,
    gate: CapabilityGate = Depends(get_capability_gate),
) -> UpdateCapabilityResponse:
    known_agents = set(get_registered_agents())
    if agent not in known_agents:
        raise HTTPException(status_code=422, detail=f"Unknown agent: {agent!r}")

    cls = get_registered_agents()[agent]
    known_intents = set(getattr(cls, "intent_map", {}))
    known_intents |= {k for k in getattr(cls, "capabilities", {})}

    if intent not in known_intents:
        raise HTTPException(status_code=422, detail=f"Unknown intent {intent!r} for agent {agent!r}")

    try:
        mode = Mode(body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid mode: {body.mode!r}") from exc

    await gate.set_permanent(agent, intent, mode)
    effective = _effective_capabilities(gate)
    return UpdateCapabilityResponse({agent: effective[agent]})
