from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

_CLIENT_VERSION = "0.1.0"
_API_VERSION = "v0"

router = APIRouter(tags=["meta"])


class VersionResponse(BaseModel):
    api_version: str
    client_version: str


@router.get(
    "/api/v0/version",
    response_model=VersionResponse,
    operation_id="getVersion",
    summary="API and client version",
    description=(
        "Returns the API version and the matching @ze/client package version. "
        "Public — no authentication required. Use to detect version skew between "
        "client and server."
    ),
)
def get_version() -> VersionResponse:
    return VersionResponse(api_version=_API_VERSION, client_version=_CLIENT_VERSION)
