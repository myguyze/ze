from __future__ import annotations

import json
from typing import Any

from ze_logging import get_logger
from ze_ingestion.types import ExtractionResult, ProcessedContent

log = get_logger(__name__)


class IngestionStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def save(
        self,
        ingestion_id: str,
        processed: ProcessedContent,
        extraction: ExtractionResult,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ingested_content
                    (id, source_url, content_type, raw_text, summary,
                     facts, entities, tags, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                ingestion_id,
                processed.source_url,
                processed.content_type.value,
                processed.text,
                extraction.summary,
                json.dumps(extraction.facts),
                json.dumps(extraction.entities),
                json.dumps(extraction.tags),
                json.dumps({**processed.metadata, **extraction.metadata}),
            )
        log.info(
            "ingestion_stored",
            id=ingestion_id,
            content_type=processed.content_type.value,
        )
