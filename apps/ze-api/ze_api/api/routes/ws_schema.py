from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import TypeAdapter

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import WsInboundFrame, WsOutboundFrame, WsSchemaResponse

router = APIRouter(tags=["schema"], dependencies=[Depends(require_api_key)])


@router.get(
    "/ws-schema",
    response_model=WsSchemaResponse,
    operation_id="getWsSchema",
    summary="WebSocket frame JSON schemas",
    description=(
        "Returns JSON Schema definitions for all WebSocket frame types. "
        "Used by the codegen script to generate TypeScript types for the client."
    ),
)
async def ws_schema() -> WsSchemaResponse:
    inbound = TypeAdapter(WsInboundFrame).json_schema()
    outbound = TypeAdapter(WsOutboundFrame).json_schema()
    return WsSchemaResponse(inbound=inbound, outbound=outbound)
