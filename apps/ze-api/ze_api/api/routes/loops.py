from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ze_api.api.dependencies import get_loop_store, get_pool, require_api_key
from ze_api.api.schemas import LoopDetail, LoopListItem, LoopTransitionResponse
from ze_worldstate import rest as loop_rest
from ze_worldstate.errors import InvalidLoopTransitionError, LoopNotFoundError
from ze_worldstate.store import LoopStore

router = APIRouter(
    prefix="/loops", tags=["loops"], dependencies=[Depends(require_api_key)]
)


@router.get(
    "",
    response_model=list[LoopListItem],
    operation_id="listLoops",
    summary="List open loops",
    description="Return open loops, optionally filtered to one lifecycle state. "
    "Defaults to non-terminal states (suspected, active, drifting).",
)
async def list_loops(
    state: str | None = Query(default=None),
    store: LoopStore = Depends(get_loop_store),
) -> list[LoopListItem]:
    states = [state] if state else None
    loops = await loop_rest.list_loops(store, states)
    return [LoopListItem.model_validate(loop) for loop in loops]


@router.get(
    "/{loop_id}",
    response_model=LoopDetail,
    operation_id="getLoop",
    summary="Get open loop detail",
    description="Return full detail for one loop, including its evidence and entity links.",
)
async def get_loop(
    loop_id: UUID,
    store: LoopStore = Depends(get_loop_store),
    pool=Depends(get_pool),
) -> LoopDetail:
    try:
        loop = await loop_rest.get_loop(store, loop_id, pool)
    except LoopNotFoundError:
        raise HTTPException(status_code=404, detail="Loop not found")
    return LoopDetail.model_validate(loop)


@router.post(
    "/{loop_id}/confirm",
    response_model=LoopTransitionResponse,
    operation_id="confirmLoop",
    summary="Confirm a suspected loop",
    description="Transition a suspected loop to active (FR-007, FR-015).",
)
async def confirm_loop(
    loop_id: UUID,
    store: LoopStore = Depends(get_loop_store),
) -> LoopTransitionResponse:
    try:
        result = await loop_rest.confirm_loop(store, loop_id)
    except LoopNotFoundError:
        raise HTTPException(status_code=404, detail="Loop not found")
    except InvalidLoopTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return LoopTransitionResponse.model_validate(result)


@router.post(
    "/{loop_id}/close",
    response_model=LoopTransitionResponse,
    operation_id="closeLoop",
    summary="Close a loop",
    description="Transition an active or drifting loop to closed (done) (FR-015).",
)
async def close_loop(
    loop_id: UUID,
    store: LoopStore = Depends(get_loop_store),
) -> LoopTransitionResponse:
    try:
        result = await loop_rest.close_loop(store, loop_id)
    except LoopNotFoundError:
        raise HTTPException(status_code=404, detail="Loop not found")
    except InvalidLoopTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return LoopTransitionResponse.model_validate(result)


@router.post(
    "/{loop_id}/drop",
    response_model=LoopTransitionResponse,
    operation_id="dropLoop",
    summary="Drop a loop",
    description="Transition any non-terminal loop to dropped (not real / no longer "
    "relevant / dismiss) (FR-007, FR-015). Records the evidence fingerprint so the "
    "same evidence does not resurface the loop later (FR-011).",
)
async def drop_loop(
    loop_id: UUID,
    store: LoopStore = Depends(get_loop_store),
) -> LoopTransitionResponse:
    try:
        result = await loop_rest.drop_loop(store, loop_id)
    except LoopNotFoundError:
        raise HTTPException(status_code=404, detail="Loop not found")
    except InvalidLoopTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return LoopTransitionResponse.model_validate(result)
