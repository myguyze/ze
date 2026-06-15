"""WebSocket entry point — FastAPI router registration."""

from __future__ import annotations

from fastapi import APIRouter

from ze_api.api.websocket.endpoint import websocket_endpoint

router = APIRouter(tags=["websocket"])
router.add_api_websocket_route("/ws", websocket_endpoint)
