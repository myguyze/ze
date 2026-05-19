from fastapi import APIRouter, Depends, HTTPException

from ze.api.dependencies import get_capability_gate, get_settings
from ze.api.openapi import OPENAPI_RESPONSES_422
from ze.api.schemas import (
    AgentCapabilityConfig,
    CapabilitiesResponse,
    CapabilityModeUpdate,
    UpdateCapabilityResponse,
)
from ze.capability.gate import CapabilityGate
from ze.settings import Settings

router = APIRouter(tags=["capabilities"])


@router.get(
    "",
    response_model=CapabilitiesResponse,
    summary="List capability modes",
    description="Return the full capabilities configuration as loaded from `capabilities.yaml`.",
)
def list_capabilities(gate: CapabilityGate = Depends(get_capability_gate)) -> CapabilitiesResponse:
    agents = gate._config.get("agents", {})
    return CapabilitiesResponse({
        agent: AgentCapabilityConfig.model_validate(
            {"enabled": cfg.get("enabled", True), **cfg.get("capabilities", {})}
        )
        for agent, cfg in agents.items()
    })


@router.put(
    "/{agent}/{intent}",
    response_model=UpdateCapabilityResponse,
    summary="Update capability mode",
    description=(
        "Set the permission mode for an agent intent. The change is written to "
        "`capabilities.yaml` atomically. Returns the updated config for that agent."
    ),
    responses=OPENAPI_RESPONSES_422,
)
def update_capability(
    agent: str,
    intent: str,
    body: CapabilityModeUpdate,
    gate: CapabilityGate = Depends(get_capability_gate),
    settings: Settings = Depends(get_settings),
) -> UpdateCapabilityResponse:
    known_agents = set(settings.agent_configs)
    if agent not in known_agents:
        raise HTTPException(status_code=422, detail=f"Unknown agent: {agent!r}")

    agent_cfg = settings.agent_configs.get(agent, {})
    known_intents = set(agent_cfg.get("intent_map", {}).keys())
    known_intents |= set(agent_cfg.get("capabilities", {}).keys())

    if intent not in known_intents:
        raise HTTPException(status_code=422, detail=f"Unknown intent {intent!r} for agent {agent!r}")

    gate.update_permanent(agent, intent, body.mode)
    updated_agent = gate._config.get("agents", {}).get(agent, {})
    updated_caps = {"enabled": updated_agent.get("enabled", True), **updated_agent.get("capabilities", {})}
    return UpdateCapabilityResponse({agent: AgentCapabilityConfig.model_validate(updated_caps)})
