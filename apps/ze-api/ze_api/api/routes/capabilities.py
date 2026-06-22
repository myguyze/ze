from fastapi import APIRouter, Depends, HTTPException

from ze_api.api.dependencies import get_capability_gate, require_api_key
from ze_api.api.openapi import OPENAPI_RESPONSES_422
from ze_api.api.schemas import (
    AgentCapabilityConfig,
    CapabilitiesResponse,
    CapabilityModeUpdate,
    UpdateCapabilityResponse,
)
from ze_agents.registry import get_registered_agents
from ze_core.capability import rest as capability_rest
from ze_core.capability.gate import CapabilityGate

router = APIRouter(tags=["capabilities"], dependencies=[Depends(require_api_key)])


@router.get(
    "",
    response_model=CapabilitiesResponse,
    operation_id="listCapabilities",
    summary="List capability modes",
    description=(
        "Return effective capability modes per agent (class defaults merged with "
        "any persistent DB overrides)."
    ),
)
def list_capabilities(gate: CapabilityGate = Depends(get_capability_gate)) -> CapabilitiesResponse:
    caps = capability_rest.effective_capabilities(gate)
    return CapabilitiesResponse({
        name: AgentCapabilityConfig.model_validate(cfg)
        for name, cfg in caps.items()
    })


@router.put(
    "/{agent}/{intent}",
    response_model=UpdateCapabilityResponse,
    operation_id="updateCapability",
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
    known_intents = set(getattr(cls, "intents", {}))
    if intent not in known_intents:
        raise HTTPException(status_code=422, detail=f"Unknown intent {intent!r} for agent {agent!r}")
    try:
        effective = await capability_rest.update_capability(gate, agent, intent, body.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid mode: {body.mode!r}") from exc
    return UpdateCapabilityResponse({
        agent: AgentCapabilityConfig.model_validate(effective[agent])
    })
