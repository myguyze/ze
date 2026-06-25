from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ze_api.api.dependencies import get_dream_store, get_pool, get_embedder, require_api_key
from ze_api.api.schemas import (
    DreamArtifactResponse,
    DreamJournalEntryResponse,
    DreamReviseRequest,
    DreamRollbackResponse,
)
from ze_memory.dream.promoter import DreamPromoter

router = APIRouter(
    prefix="/memory/dream",
    tags=["dream"],
    dependencies=[Depends(require_api_key)],
)


def _get_promoter(pool=Depends(get_pool), dream_store=Depends(get_dream_store), embedder=Depends(get_embedder)) -> DreamPromoter:
    return DreamPromoter(pool=pool, dream_store=dream_store, embedder=embedder)


@router.get(
    "/journal",
    response_model=list[DreamJournalEntryResponse],
    operation_id="listDreamJournal",
    summary="List dream journal entries",
    description="Return recent dream journal entries, newest first.",
)
async def list_dream_journal(
    limit: int = 10,
    dream_store=Depends(get_dream_store),
) -> list[DreamJournalEntryResponse]:
    entries = await dream_store.list_journal_entries(limit=limit)
    return [DreamJournalEntryResponse.model_validate(e) for e in entries]


@router.get(
    "/artifacts",
    response_model=list[DreamArtifactResponse],
    operation_id="listDreamArtifacts",
    summary="List artifacts pending review",
    description="Return staged dream artifacts with status=needs_review.",
)
async def list_dream_artifacts(
    dream_store=Depends(get_dream_store),
) -> list[DreamArtifactResponse]:
    rows = await dream_store.get_needs_review_artifacts()
    return [DreamArtifactResponse.model_validate(r) for r in rows]


@router.get(
    "/artifacts/{artifact_id}",
    response_model=DreamArtifactResponse,
    operation_id="getDreamArtifact",
    summary="Get dream artifact detail",
    description="Return a single dream artifact with its scoring results.",
)
async def get_dream_artifact(
    artifact_id: UUID,
    dream_store=Depends(get_dream_store),
) -> DreamArtifactResponse:
    row = await dream_store.get_artifact_row(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return DreamArtifactResponse.model_validate(row)


@router.post(
    "/artifacts/{artifact_id}/approve",
    response_model=DreamArtifactResponse,
    operation_id="approveDreamArtifact",
    summary="Approve a dream artifact",
    description="Promote the artifact to long-term memory.",
)
async def approve_dream_artifact(
    artifact_id: UUID,
    promoter: DreamPromoter = Depends(_get_promoter),
    dream_store=Depends(get_dream_store),
) -> DreamArtifactResponse:
    row = await dream_store.get_artifact_row(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await promoter.apply_user_decision(artifact_id, "approve")
    updated = await dream_store.get_artifact_row(artifact_id)
    return DreamArtifactResponse.model_validate(updated)


@router.post(
    "/artifacts/{artifact_id}/reject",
    response_model=DreamArtifactResponse,
    operation_id="rejectDreamArtifact",
    summary="Reject a dream artifact",
    description="Mark the artifact rejected and decrement source episode retrieval weight.",
)
async def reject_dream_artifact(
    artifact_id: UUID,
    promoter: DreamPromoter = Depends(_get_promoter),
    dream_store=Depends(get_dream_store),
) -> DreamArtifactResponse:
    row = await dream_store.get_artifact_row(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await promoter.apply_user_decision(artifact_id, "reject")
    updated = await dream_store.get_artifact_row(artifact_id)
    return DreamArtifactResponse.model_validate(updated)


@router.post(
    "/artifacts/{artifact_id}/revise",
    response_model=DreamArtifactResponse,
    operation_id="reviseDreamArtifact",
    summary="Revise and promote a dream artifact",
    description="Replace the artifact content with a user-edited version, then promote it.",
)
async def revise_dream_artifact(
    artifact_id: UUID,
    body: DreamReviseRequest,
    promoter: DreamPromoter = Depends(_get_promoter),
    dream_store=Depends(get_dream_store),
) -> DreamArtifactResponse:
    row = await dream_store.get_artifact_row(artifact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    await promoter.apply_user_decision(artifact_id, "revise", revised_content=body.content)
    updated = await dream_store.get_artifact_row(artifact_id)
    return DreamArtifactResponse.model_validate(updated)


@router.post(
    "/runs/{run_id}/rollback",
    response_model=DreamRollbackResponse,
    operation_id="rollbackDreamRun",
    summary="Roll back a dream run",
    description=(
        "Bulk-mark all promoted artifacts from the run as rolled_back, "
        "contradict promoted facts, and flag contaminated session summaries for re-summarisation."
    ),
)
async def rollback_dream_run(
    run_id: UUID,
    promoter: DreamPromoter = Depends(_get_promoter),
) -> DreamRollbackResponse:
    result = await promoter.rollback_run(run_id)
    return DreamRollbackResponse(**result)
