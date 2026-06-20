from __future__ import annotations

import json

from ze_agents.logging import get_logger
from ze_ingestion.types import ContentType, ExtractionResult, ProcessedContent

log = get_logger(__name__)

_EXTRACT_PROMPT = """\
You are an information extraction assistant. Given the following content, extract:
1. A concise summary (2-4 sentences)
2. Key facts as a list of plain-English statements
3. Named entities (people, organisations, places, products)
4. Relevant tags / topics

Respond with valid JSON matching exactly this schema:
{
  "summary": "...",
  "facts": ["fact1", "fact2", ...],
  "entities": ["Entity1", "Entity2", ...],
  "tags": ["tag1", "tag2", ...]
}

Content:
"""


class LLMExtractor:
    """Default extractor — works on any content type via LLM."""

    content_types: list[ContentType] = []

    def __init__(self, llm_client: object, model: str) -> None:
        self._client = llm_client
        self._model = model

    async def extract(self, content: ProcessedContent) -> ExtractionResult:
        text = content.text[:12_000]
        messages = [{"role": "user", "content": _EXTRACT_PROMPT + text}]
        try:
            raw = await self._client.complete(  # type: ignore[attr-defined]
                model=self._model,
                messages=messages,
            )
            data = json.loads(raw)
        except Exception as exc:
            log.warning("llm_extractor_failed", error=str(exc))
            return ExtractionResult(summary="", facts=[], entities=[], tags=[])

        return ExtractionResult(
            summary=data.get("summary", ""),
            facts=data.get("facts", []),
            entities=data.get("entities", []),
            tags=data.get("tags", []),
        )
