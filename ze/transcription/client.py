import base64

import structlog

from ze.openrouter.client import OpenRouterClient
from ze.telemetry.context import set_agent_context, set_flow_context
from ze.transcription.types import TranscriptionResult


class TranscriptionClient:
    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        model: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self._client = openrouter_client
        self._model = model
        self._log = logger

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str,
    ) -> TranscriptionResult:
        set_flow_context("transcription")
        set_agent_context("whisper")
        message = {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(audio_bytes).decode(),
                        "format": audio_format,
                    },
                }
            ],
        }
        text = await self._client.complete(
            messages=[message],
            model=self._model,
        )
        self._log.info(
            "transcription_complete",
            model=self._model,
            audio_bytes=len(audio_bytes),
            audio_format=audio_format,
        )
        return TranscriptionResult(text=text.strip())
