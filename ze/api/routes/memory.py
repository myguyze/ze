from fastapi import APIRouter, Depends, HTTPException

from ze.api.dependencies import get_memory_consolidator, get_pool
from ze.api.openapi import OPENAPI_RESPONSES_422
from ze.api.schemas import (
    ConsolidationReportResponse,
    FactReviewRequest,
    MemoryDigestResponse,
    UserFactResponse,
)

router = APIRouter(tags=["memory"])


@router.get(
    "/facts",
    response_model=list[UserFactResponse],
    summary="List user facts",
    description="Return all user facts, reviewed and unreviewed, newest first.",
)
async def list_facts(pool=Depends(get_pool)) -> list[UserFactResponse]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, key, value, agent, confidence, reviewed, contradicted, updated_at "
            "FROM user_facts ORDER BY updated_at DESC"
        )
    return [UserFactResponse.model_validate(dict(r)) for r in rows]


@router.post(
    "/facts/review",
    response_model=list[UserFactResponse],
    summary="Review user facts",
    description=(
        "Apply confirm, reject, or edit actions to user facts. Confirm and edit set "
        "`reviewed=true`; reject deletes the row. Edit requires `value` in the action."
    ),
    responses=OPENAPI_RESPONSES_422,
)
async def review_facts(
    body: FactReviewRequest, pool=Depends(get_pool)
) -> list[UserFactResponse]:
    updated: list[UserFactResponse] = []
    async with pool.acquire() as conn:
        for action in body.actions:
            if action.action == "reject":
                await conn.execute(
                    "DELETE FROM user_facts WHERE id = $1", action.id
                )
            elif action.action == "confirm":
                row = await conn.fetchrow(
                    "UPDATE user_facts SET reviewed = true, expires_at = NULL WHERE id = $1 RETURNING *",
                    action.id,
                )
                if row:
                    updated.append(UserFactResponse.model_validate(dict(row)))
            elif action.action == "edit":
                if action.value is None:
                    raise HTTPException(status_code=422, detail="value required for edit action")
                row = await conn.fetchrow(
                    "UPDATE user_facts SET value = $1, reviewed = true WHERE id = $2 RETURNING *",
                    action.value,
                    action.id,
                )
                if row:
                    updated.append(UserFactResponse.model_validate(dict(row)))
    return updated


@router.get(
    "/digest",
    response_model=MemoryDigestResponse,
    summary="Memory digest",
    description=(
        "Snapshot for the memory UI: unreviewed facts, contradicted facts, and the "
        "10 most recent episodes."
    ),
)
async def memory_digest(pool=Depends(get_pool)) -> MemoryDigestResponse:
    async with pool.acquire() as conn:
        unreviewed = await conn.fetch(
            "SELECT id, key, value, agent FROM user_facts WHERE reviewed = false ORDER BY updated_at DESC"
        )
        contradicted = await conn.fetch(
            "SELECT id, key, value, agent FROM user_facts WHERE contradicted = true ORDER BY updated_at DESC"
        )
        episodes = await conn.fetch(
            "SELECT id, agent, summary, created_at FROM episodes ORDER BY created_at DESC LIMIT 10"
        )
        expiring = await conn.fetch(
            "SELECT id, key, value, agent, expires_at FROM user_facts "
            "WHERE expires_at IS NOT NULL AND expires_at > NOW() ORDER BY expires_at ASC"
        )
    return MemoryDigestResponse(
        unreviewed_facts=[dict(r) for r in unreviewed],
        contradicted_facts=[dict(r) for r in contradicted],
        recent_episodes=[dict(r) for r in episodes],
        expiring_facts=[dict(r) for r in expiring],
    )


@router.post(
    "/consolidate",
    response_model=ConsolidationReportResponse,
    summary="Trigger memory consolidation",
    description=(
        "Run dedup, expiry, and episode archival immediately. "
        "Returns a report of all changes made."
    ),
)
async def run_consolidation(
    consolidator=Depends(get_memory_consolidator),
) -> ConsolidationReportResponse:
    report = await consolidator.run()
    return ConsolidationReportResponse(
        facts_merged=report.facts_merged,
        facts_soft_expired=report.facts_soft_expired,
        facts_hard_deleted=report.facts_hard_deleted,
        episodes_archived=report.episodes_archived,
        episodes_deleted=report.episodes_deleted,
        duration_ms=report.duration_ms,
    )
