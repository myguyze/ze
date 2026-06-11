from __future__ import annotations

import base64
from typing import Any

from langchain_core.runnables import RunnableConfig

from ze_core.defaults import MODEL_VISION_CAPTION, MODEL_WHISPER
from ze_core.logging import get_logger
from ze_core.openrouter.client import _normalise_audio_format
from ze_core.orchestration.state import AgentState

log = get_logger(__name__)


async def preprocess(state: AgentState, config: RunnableConfig) -> dict:
    """Normalise multimodal input before routing.

    - Audio → transcribed to text via openrouter_client.transcribe(); audio bytes
      are cleared from state so they are not persisted in the checkpoint.
    - Image without prompt → vision caption generated for routing; stored as
      image_caption. image_data is preserved for the execution node.
    - Image with prompt → image_caption is set to the user's prompt text.
    - Text-only → no-op pass-through.
    """
    client = config["configurable"]["openrouter_client"]
    cfg = config["configurable"].get("settings") or {}
    models = (
        cfg.get("models", {})
        if isinstance(cfg, dict)
        else getattr(cfg, "config", {}).get("models", {})
    )
    updates: dict = {}

    if state.get("audio_data"):
        from ze_core.telemetry.context import set_agent_context, set_flow_context
        set_flow_context("transcription")
        set_agent_context("whisper")

        model = models.get("whisper", MODEL_WHISPER)
        fmt = _normalise_audio_format(state.get("audio_mime") or "audio/ogg")
        text = await client.transcribe(state["audio_data"], fmt, model=model)

        updates["prompt"] = text
        updates["input_modality"] = "voice"
        updates["audio_data"] = None
        updates["audio_mime"] = None
        log.info("preprocess_transcribed", chars=len(text))

    elif state.get("image_data"):
        if not state.get("prompt"):
            model = models.get("vision_caption", MODEL_VISION_CAPTION)
            caption = await _vision_caption(state["image_data"], state["image_mime"], client, model)
            updates["image_caption"] = caption
            log.info("preprocess_captioned", chars=len(caption))
        else:
            updates["image_caption"] = state["prompt"]

    return updates


async def _vision_caption(
    image_data: bytes,
    image_mime: str | None,
    client: Any,
    model: str,
) -> str:
    mime = image_mime or "image/jpeg"
    message = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(image_data).decode()}",
                    "detail": "low",
                },
            },
            {"type": "text", "text": "Describe this image in one sentence for intent classification."},
        ],
    }
    return await client.complete(messages=[message], model=model, max_tokens=80)


