from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ze_api.api.dependencies import get_container, get_memory_consolidator, require_api_key
from ze_api.api.openapi import OPENAPI_RESPONSES_422
from ze_api.api.schemas import (
    ConsolidationReportResponse,
    EntityDetailResponse,
    FactReviewRequest,
    MemoryDigestResponse,
    MemoryFactQualityResponse,
    MemoryFeedItem,
    MemoryFeedResponse,
    MemoryGraphResponse,
    TimelineBoundsResponse,
    UserFactResponse,
    UserProfileResponse,
)
from ze_memory import admin as memory_admin

router = APIRouter(tags=["memory"], dependencies=[Depends(require_api_key)])


@router.get(
    "/feed",
    response_model=MemoryFeedResponse,
    operation_id="getMemoryFeed",
    summary="Memory feed",
    description=(
        "Reverse-chronological stream of facts and episodes. "
        "Cursor-paginated via the `before` timestamp. "
        "Filter by `type` (fact/episode/all) and `agent`. "
        "Pass `as_of` to get a point-in-time snapshot of Ze's memory."
    ),
)
async def get_memory_feed(
    limit: int = Query(default=50, ge=1, le=200, description="Max items per page"),
    before: datetime | None = Query(default=None, description="Return items older than this timestamp"),
    type: Literal["fact", "episode", "all"] = Query(default="all", description="Filter by item type"),
    agent: str | None = Query(default=None, description="Filter by originating agent name"),
    as_of: datetime | None = Query(default=None, description="Return only items that existed at this point in time"),
    container=Depends(get_container),
) -> MemoryFeedResponse:
    result = await memory_admin.get_memory_feed(
        container.pool,
        limit=limit,
        before=before,
        type_filter=type,
        agent_filter=agent,
        as_of=as_of,
    )
    return MemoryFeedResponse.model_validate(result)


@router.get(
    "/timeline-bounds",
    response_model=TimelineBoundsResponse,
    operation_id="getMemoryTimelineBounds",
    summary="Memory timeline bounds",
    description=(
        "Returns the earliest and latest memory timestamps. "
        "Use to configure the date scrubber range on the memory feed page."
    ),
)
async def get_memory_timeline_bounds(container=Depends(get_container)) -> TimelineBoundsResponse:
    result = await memory_admin.get_memory_timeline_bounds(container.pool)
    return TimelineBoundsResponse.model_validate(result)


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
    response_model=list[MemoryFeedItem],
    operation_id="reviewFacts",
    summary="Review memory facts",
    description=(
        "Apply confirm, reject, or edit actions to memory facts. Confirm and edit set "
        "`reviewed=true`; reject deletes the row. Edit requires `value` in the action."
    ),
    responses=OPENAPI_RESPONSES_422,
)
async def review_facts(
    body: FactReviewRequest,
    container=Depends(get_container),
) -> list[MemoryFeedItem]:
    for action in body.actions:
        if action.action == "edit" and action.value is None:
            raise HTTPException(status_code=422, detail="value required for edit action")
    updated = await memory_admin.review_facts(container.pool, body.actions)
    return [MemoryFeedItem.model_validate(r) for r in updated]


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


@router.get(
    "/graph",
    response_model=MemoryGraphResponse,
    operation_id="getMemoryGraph",
    summary="Memory entity graph",
    description=(
        "Returns top-N entities by relationship count, plus all entity-to-entity "
        "edges between them. Pass `seed_id` to expand from a specific entity."
    ),
)
async def get_memory_graph(
    limit: int = Query(default=50, ge=1, le=200, description="Max entities to return"),
    entity_type: str | None = Query(default=None, description="Filter by entity type"),
    seed_id: UUID | None = Query(default=None, description="Expand 1-hop from this entity"),
    container=Depends(get_container),
) -> MemoryGraphResponse:
    result = await memory_admin.get_memory_graph(
        container.pool,
        limit=limit,
        entity_type=entity_type,
        seed_id=seed_id,
    )
    return MemoryGraphResponse.model_validate(result)


@router.get(
    "/graph/entity/{entity_id}",
    response_model=EntityDetailResponse,
    operation_id="getEntityDetail",
    summary="Entity detail",
    description=(
        "Facts, episodes, and 1-hop neighbours for a selected entity. "
        "Use `neighbours` and `neighbour_edges` to expand the graph."
    ),
)
async def get_entity_detail(
    entity_id: UUID,
    container=Depends(get_container),
) -> EntityDetailResponse:
    result = await memory_admin.get_entity_detail(container.pool, entity_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return EntityDetailResponse.model_validate(result)
