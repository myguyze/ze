from fastapi import APIRouter, Depends, HTTPException

from ze_api.api.dependencies import get_container, get_memory_consolidator, require_api_key
from ze_api.api.openapi import OPENAPI_RESPONSES_422
from ze_api.api.schemas import (
    ConsolidationReportResponse,
    FactReviewRequest,
    MemoryDigestResponse,
    MemoryFactQualityResponse,
    UserFactResponse,
    UserProfileResponse,
)
from ze_memory import admin as memory_admin

router = APIRouter(tags=["memory"], dependencies=[Depends(require_api_key)])


@router.get(
    "/facts",
    response_model=list[UserFactResponse],
    operation_id="listFacts",
    summary="List user facts",
    description="Return all user facts, reviewed and unreviewed, newest first.",
)
async def list_facts(container=Depends(get_container)) -> list[UserFactResponse]:
    rows = await memory_admin.list_facts(container.pool)
    return [UserFactResponse.model_validate(r) for r in rows]


@router.post(
    "/facts/review",
    response_model=list[UserFactResponse],
    operation_id="reviewFacts",
    summary="Review user facts",
    description=(
        "Apply confirm, reject, or edit actions to user facts. Confirm and edit set "
        "`reviewed=true`; reject deletes the row. Edit requires `value` in the action."
    ),
    responses=OPENAPI_RESPONSES_422,
)
async def review_facts(
    body: FactReviewRequest,
    container=Depends(get_container),
) -> list[UserFactResponse]:
    for action in body.actions:
        if action.action == "edit" and action.value is None:
            raise HTTPException(status_code=422, detail="value required for edit action")
    updated = await memory_admin.review_facts(container.pool, body.actions)
    return [UserFactResponse.model_validate(r) for r in updated]


@router.get(
    "/digest",
    response_model=MemoryDigestResponse,
    operation_id="getMemoryDigest",
    summary="Memory digest",
    description=(
        "Snapshot for the memory UI: unreviewed facts, contradicted facts, and the "
        "10 most recent episodes."
    ),
)
async def get_memory_digest(container=Depends(get_container)) -> MemoryDigestResponse:
    digest = await memory_admin.get_memory_digest(container.pool)
    return MemoryDigestResponse.model_validate(digest)


@router.post(
    "/consolidate",
    response_model=ConsolidationReportResponse,
    operation_id="consolidateMemory",
    summary="Trigger memory consolidation",
    description=(
        "Run dedup, expiry, and episode archival immediately. "
        "Returns a report of all changes made."
    ),
)
async def consolidate_memory(consolidator=Depends(get_memory_consolidator)) -> ConsolidationReportResponse:
    report = await consolidator.run()
    return ConsolidationReportResponse(
        facts_merged=report.facts_merged,
        facts_soft_expired=report.facts_soft_expired,
        facts_hard_deleted=report.facts_hard_deleted,
        episodes_archived=report.episodes_archived,
        episodes_deleted=report.episodes_deleted,
        session_episodes_archived=report.session_episodes_archived,
        profile_updated=report.profile_updated,
        duration_ms=report.duration_ms,
    )


@router.get(
    "/facts/quality",
    response_model=MemoryFactQualityResponse,
    operation_id="getFactQuality",
    summary="Memory fact quality audit",
    description=(
        "Diagnostic snapshot of memory_facts health: distribution by provenance, "
        "confidence stats, contradicted count, and synthesized-fact lifecycle status. "
        "Use to assess source pool quality before trusting dream synthesis output."
    ),
)
async def get_fact_quality(container=Depends(get_container)) -> MemoryFactQualityResponse:
    async with container.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                                          AS total,
                COUNT(*) FILTER (WHERE provenance = 'raw')                        AS raw_count,
                COUNT(*) FILTER (WHERE provenance = 'synthesized')                AS synthesized_count,
                COALESCE(AVG(confidence), 0.0)                                    AS avg_confidence,
                COUNT(*) FILTER (WHERE confidence < 0.5)                          AS low_confidence_count,
                COUNT(*) FILTER (WHERE contradicted = true)                       AS contradicted_count,
                COUNT(*) FILTER (WHERE provenance = 'synthesized'
                                   AND reviewed = false)                          AS synthesized_unreviewed,
                COUNT(*) FILTER (WHERE provenance = 'synthesized'
                                   AND corroborated = false
                                   AND contradicted = false)                      AS synthesized_uncorroborated,
                COUNT(*) FILTER (WHERE provenance = 'synthesized'
                                   AND valid_until IS NOT NULL
                                   AND valid_until < now()
                                   AND contradicted = false)                      AS synthesized_expired
            FROM memory_facts
            """
        )
    return MemoryFactQualityResponse(
        total=row["total"],
        by_provenance={"raw": row["raw_count"], "synthesized": row["synthesized_count"]},
        avg_confidence=round(float(row["avg_confidence"]), 4),
        low_confidence_count=row["low_confidence_count"],
        contradicted_count=row["contradicted_count"],
        synthesized_unreviewed=row["synthesized_unreviewed"],
        synthesized_uncorroborated=row["synthesized_uncorroborated"],
        synthesized_expired=row["synthesized_expired"],
    )


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    operation_id="getProfile",
    summary="Current user profile",
    description=(
        "The synthesised user profile — preferences, habits, topics, relationships, "
        "and goals. Updated nightly by the consolidation job."
    ),
)
async def get_profile(container=Depends(get_container)) -> UserProfileResponse:
    row = await memory_admin.get_profile(container.pool)
    if row is None:
        raise HTTPException(status_code=404, detail="No profile synthesised yet")
    return UserProfileResponse.model_validate(row)
