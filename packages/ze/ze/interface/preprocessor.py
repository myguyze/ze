from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ze.logging import get_logger
from ze_core.interface.types import ProcessedInput, RawInput

if TYPE_CHECKING:
    from ze.transcription.client import TranscriptionClient

log = get_logger(__name__)


class TelegramInputPreprocessor:
    """Normalises Telegram RawInput to a routing-ready ProcessedInput."""

    def __init__(
        self,
        transcription_client: TranscriptionClient | None = None,
    ) -> None:
        self._transcription = transcription_client

    async def process(self, raw: RawInput, client: Any) -> ProcessedInput:
        del client  # vision caption runs in embed_route; Whisper uses transcription client

        if raw.audio:
            if self._transcription is None:
                raise RuntimeError("voice input requires a TranscriptionClient")
            mime = raw.audio_mime or "audio/ogg"
            fmt = "ogg" if "ogg" in mime else "mp3"
            duration = None
            result = await self._transcription.transcribe(
                raw.audio,
                fmt,
                duration_seconds=duration,
            )
            return ProcessedInput(
                prompt=result.text,
                input_modality="voice",
            )

        if raw.image:
            return ProcessedInput(
                prompt=raw.text or "",
                input_modality="image",
                image_data=raw.image,
                image_mime=raw.image_mime or "image/jpeg",
            )

        return ProcessedInput(
            prompt=raw.text or "",
            input_modality="text",
        )
