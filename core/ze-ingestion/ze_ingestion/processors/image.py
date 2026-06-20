from __future__ import annotations

import base64

from ze_ingestion.errors import ProcessError
from ze_ingestion.types import ContentType, ProcessedContent, RawContent

_VISION_MODEL = "google/gemini-flash-1.5"


class ImageProcessor:
    """Describes image content via a vision LLM (injected LLMClient)."""

    content_types: list[ContentType] = [ContentType.IMAGE]

    def __init__(self, llm_client: object) -> None:
        self._client = llm_client

    async def process(self, raw: RawContent) -> ProcessedContent:
        try:
            b64 = base64.b64encode(raw.data).decode()
            response = await self._client.complete(  # type: ignore[attr-defined]
                model=_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{raw.mime_type};base64,{b64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Describe this image in detail. "
                                    "Include all visible text, objects, people, and context."
                                ),
                            },
                        ],
                    }
                ],
            )
            text = response.strip() if isinstance(response, str) else ""
        except Exception as exc:
            raise ProcessError(f"Image description failed: {exc}") from exc

        return ProcessedContent(
            content_type=raw.content_type,
            source_url=raw.source_url,
            text=text,
            metadata={"vision_described": True},
        )
