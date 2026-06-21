from __future__ import annotations

from fastapi import APIRouter

from ze_api.api.schemas import HealthResponse

router = APIRouter(tags=["meta"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="healthCheck",
    summary="Health check",
    description=(
        "Verifies the server is reachable. Public — no authentication required. "
        "Used by the web client during onboarding and settings connection tests."
    ),
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
