from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from ze_api.api.schemas import DeleteIntentResponse, DeleteRequest, ImportResponse
from ze_api.logging import get_logger
from ze_data.portability.service import DataPortabilityService, InstanceNotEmptyError, SchemaMismatchError

log = get_logger(__name__)

router = APIRouter(tags=["data"])


def _auth(request: Request, authorization: str | None) -> None:
    settings = request.app.state.settings
    bearer = (
        authorization.removeprefix("Bearer ").strip()
        if authorization and authorization.startswith("Bearer ")
        else ""
    )
    if bearer != settings.ze_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _service(request: Request) -> DataPortabilityService:
    return request.app.state.data_portability_service


@router.get(
    "/api/data/export",
    summary="Export all user data",
    description=(
        "Produces a versioned ZIP archive containing all personal data stored by Ze, "
        "one JSON file per data domain. The manifest includes the current schema revisions "
        "so the archive can be validated at import time."
    ),
    response_class=Response,
)
async def export_data(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _auth(request, authorization)
    log.info("data_export_requested")
    archive = await _service(request).export()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="ze-export-{ts}.zip"'},
    )


@router.post(
    "/api/data/import",
    response_model=ImportResponse,
    summary="Import a data archive",
    description=(
        "Restores a previously exported ZIP archive into this Ze instance. "
        "The archive's schema_revisions must match the current schema exactly. "
        "The instance must be empty — delete all data first if needed."
    ),
)
async def import_data(
    request: Request,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
) -> ImportResponse:
    _auth(request, authorization)
    log.info("data_import_requested", filename=file.filename)
    archive_bytes = await file.read()
    try:
        result = await _service(request).import_archive(archive_bytes)
    except SchemaMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except InstanceNotEmptyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return ImportResponse(
        domains_imported=result.domains_imported,
        rows_imported=result.rows_imported,
    )


@router.post(
    "/api/data/delete-intent",
    response_model=DeleteIntentResponse,
    summary="Issue a deletion confirmation token",
    description=(
        "Mints a short-lived token (valid for 10 minutes) required by DELETE /api/data. "
        "The web client calls this first, prompts the user to confirm, then calls DELETE /api/data."
    ),
    status_code=201,
)
async def create_delete_intent(
    request: Request,
    authorization: str | None = Header(default=None),
) -> DeleteIntentResponse:
    _auth(request, authorization)
    token, expiry = _service(request).create_delete_intent()
    log.info("delete_intent_issued")
    return DeleteIntentResponse(
        confirmation_token=token,
        expires_at=expiry.isoformat(),
    )


@router.delete(
    "/api/data",
    summary="Hard-delete all user data",
    description=(
        "Permanently deletes every row of user data across all Ze tables. "
        "Requires a valid confirmation_token from POST /api/data/delete-intent."
    ),
    status_code=204,
)
async def delete_data(
    body: DeleteRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    _auth(request, authorization)
    if not _service(request).consume_delete_intent(body.confirmation_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired confirmation token",
        )
    log.info("data_deletion_started")
    await _service(request).delete()
    return Response(status_code=204)
