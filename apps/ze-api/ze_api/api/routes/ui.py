from fastapi import APIRouter, Depends, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import UiManifestResponse

router = APIRouter(prefix="/api/v0/ui", tags=["ui"])


@router.get(
    "/manifest",
    response_model=UiManifestResponse,
    operation_id="getUiManifest",
    summary="UI shell manifest",
    description=(
        "Returns plugin-contributed nav entries and settings sections. "
        "Core routes (chat, goals, settings) are not included — they are "
        "hardcoded in the web client."
    ),
)
async def get_ui_manifest(
    request: Request,
    _: str = Depends(require_api_key),
) -> UiManifestResponse:
    manifest = request.app.state.container.ui_manifest
    return UiManifestResponse.from_domain(manifest)
