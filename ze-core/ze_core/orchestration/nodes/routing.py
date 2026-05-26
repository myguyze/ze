from __future__ import annotations

import base64
from typing import Any

from ze_core.logging import get_logger
from ze_core.orchestration.state import AgentState

log = get_logger(__name__)

_DEFAULT_CAPTION_MODEL = "google/gemini-flash-1.5"


async def _vision_caption(
    image_data: bytes,
    image_mime: str,
    client: Any,
    model: str,
) -> str:
    message = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_mime};base64,{base64.b64encode(image_data).decode()}",
                    "detail": "low",
                },
            },
            {"type": "text", "text": "Describe this image in one sentence for intent classification."},
        ],
    }
    return await client.complete(messages=[message], model=model, max_tokens=80)


async def embed_route(state: AgentState, config: dict) -> dict:
    from ze_core.routing.router import EmbeddingRouter

    router: EmbeddingRouter = config["configurable"]["router"]
    updates: dict = {}
    routing_text = state["prompt"]

    if state.get("input_modality") == "image" and not state.get("prompt"):
        client = config["configurable"]["openrouter_client"]
        cfg = config["configurable"].get("settings") or {}
        models = cfg.get("models", {}) if isinstance(cfg, dict) else getattr(cfg, "config", {}).get("models", {})
        caption_model = models.get("vision_caption", _DEFAULT_CAPTION_MODEL)
        caption = await _vision_caption(state["image_data"], state["image_mime"], client, caption_model)
        routing_text = caption
        updates["image_caption"] = caption
    elif state.get("input_modality") == "image":
        updates["image_caption"] = state["prompt"]

    envelope = await router.route(prompt=routing_text, session_id=state["session_id"])
    log.info(
        "orchestration_routed",
        session_id=state["session_id"],
        primary_agent=envelope.primary_agent,
        routing_method=envelope.routing_method,
        is_compound=envelope.is_compound,
    )
    updates["envelope"] = envelope
    return updates


async def decompose(state: AgentState, config: dict) -> dict:
    return {}
