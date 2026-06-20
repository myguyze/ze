from __future__ import annotations

import base64

from ze_ingestion.errors import ProcessError
from ze_ingestion.types import ContentType, ProcessedContent, RawContent


class AudioProcessor:
    """Transcribes audio via OpenRouter Whisper (injected LLMClient)."""

    content_types: list[ContentType] = [ContentType.AUDIO]

    def __init__(self, llm_client: object) -> None:
        self._client = llm_client

    async def process(self, raw: RawContent) -> ProcessedContent:
        try:
            b64 = base64.b64encode(raw.data).decode()
            response = await self._client.complete(  # type: ignore[attr-defined]
                model="openai/whisper-large-v3",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": b64,
                                    "format": raw.mime_type.split("/")[-1] or "mp3",
                                },
                            }
                        ],
                    }
                ],
            )
            text = response.strip() if isinstance(response, str) else ""
        except Exception as exc:
            raise ProcessError(f"Audio transcription failed: {exc}") from exc

        return ProcessedContent(
            content_type=raw.content_type,
            source_url=raw.source_url,
            text=text,
            metadata={"transcribed": True},
        )
