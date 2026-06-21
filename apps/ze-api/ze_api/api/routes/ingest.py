from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ze_api.api.dependencies import require_api_key
from ze_ingestion.types import IngestionRequest

router = APIRouter(tags=["ingestion"], dependencies=[Depends(require_api_key)])


class IngestResponse(BaseModel):
    ingestion_id: str
    content_type: str
    summary: str
    facts_count: int
    tags: list[str]


@router.post(
    "/ingest",
    response_model=IngestResponse,
    operation_id="ingest",
    summary="Ingest content",
    description=(
        "Fetch, process, and ingest a URL or uploaded file into Ze's memory. "
        "Exactly one of 'url' or 'file' must be provided."
    ),
)
async def ingest(
    request: Request,
    url: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    label: str | None = Form(default=None),
) -> IngestResponse:
    if not url and not file:
        raise HTTPException(status_code=422, detail="Provide either 'url' or 'file'")
    if url and file:
        raise HTTPException(status_code=422, detail="Provide only one of 'url' or 'file'")

    file_bytes: bytes | None = None
    mime_type: str | None = None
    if file is not None:
        file_bytes = await file.read()
        mime_type = file.content_type

    pipeline = request.app.state.container.ingestion_pipeline
    result = await pipeline.ingest(
        IngestionRequest(
            url=url,
            file_bytes=file_bytes,
            mime_type=mime_type,
            label=label,
        )
    )
    return IngestResponse(
        ingestion_id=result.ingestion_id,
        content_type=result.content_type.value,
        summary=result.summary,
        facts_count=result.facts_count,
        tags=result.tags,
    )
