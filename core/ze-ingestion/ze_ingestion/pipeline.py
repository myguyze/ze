from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any

from ze_logging import get_logger
from ze_ingestion.classifier import ContentClassifier
from ze_ingestion.errors import UnsupportedContentError
from ze_ingestion.extractors import Extractor
from ze_ingestion.fetchers import Fetcher
from ze_ingestion.processors import Processor
from ze_ingestion.types import (
    ContentType,
    ExtractionResult,
    IngestionRequest,
    IngestionResult,
    ProcessedContent,
    RawContent,
)

log = get_logger(__name__)


def _merge_results(results: list[ExtractionResult]) -> ExtractionResult:
    summaries = [r.summary for r in results if r.summary]
    facts = list(dict.fromkeys(f for r in results for f in r.facts))
    entities = list(dict.fromkeys(e for r in results for e in r.entities))
    tags = list(dict.fromkeys(t for r in results for t in r.tags))
    metadata: dict[str, Any] = {}
    for r in results:
        metadata.update(r.metadata)
    return ExtractionResult(
        summary="\n\n".join(summaries),
        facts=facts,
        entities=entities,
        tags=tags,
        metadata=metadata,
    )


class IngestionPipeline:
    def __init__(
        self,
        classifier: ContentClassifier,
        fetchers: list[Fetcher],
        processors: list[Processor],
        extractors: list[Extractor],
        store: Any,
        memory_sink: Any,
    ) -> None:
        self._classifier = classifier
        self._fetchers = fetchers
        self._processors = processors
        self._extractors = extractors
        self._store = store
        self._sink = memory_sink

    def _pick_fetcher(self, url: str) -> Fetcher:
        for fetcher in self._fetchers:
            for pattern in fetcher.url_patterns:
                if re.search(pattern, url, re.I):
                    return fetcher
        raise UnsupportedContentError(f"No fetcher matched URL: {url}")

    def _pick_processor(self, content_type: ContentType) -> Processor:
        for proc in self._processors:
            if content_type in proc.content_types:
                return proc
        for proc in self._processors:
            if ContentType.UNKNOWN in proc.content_types:
                return proc
        raise UnsupportedContentError(f"No processor for content type: {content_type}")

    def _matching_extractors(self, content_type: ContentType) -> list[Extractor]:
        matched = [
            e for e in self._extractors
            if not e.content_types or content_type in e.content_types
        ]
        return matched or self._extractors[:1]

    async def ingest(
        self,
        request: IngestionRequest,
        reporter: Any = None,
    ) -> IngestionResult:
        async def emit(key: str) -> None:
            if reporter is not None:
                await reporter.emit(key)

        # 1. Classify
        await emit("ingestion.classifying")
        content_type = self._classifier.classify(
            url=request.url,
            mime_type=request.mime_type,
            data=request.file_bytes,
        )

        # 2. Fetch
        raw: RawContent
        if request.url:
            await emit("ingestion.fetching")
            fetcher = self._pick_fetcher(request.url)
            raw = await fetcher.fetch(request.url)
            if raw.content_type == ContentType.UNKNOWN or content_type == ContentType.UNKNOWN:
                content_type = self._classifier.classify(
                    url=request.url,
                    mime_type=raw.mime_type,
                    data=raw.data[:512],
                ) or ContentType.UNKNOWN
            raw.content_type = content_type
        else:
            raw = RawContent(
                content_type=content_type,
                source_url=None,
                data=request.file_bytes or b"",
                mime_type=request.mime_type or "application/octet-stream",
            )

        # 3. Process
        await emit(f"ingestion.processing.{content_type.value}")
        processor = self._pick_processor(content_type)
        processed: ProcessedContent = await processor.process(raw)

        # 4. Extract (all matching, in parallel)
        await emit("ingestion.extracting")
        matched = self._matching_extractors(content_type)

        async def _safe_extract(extractor: Extractor) -> ExtractionResult | None:
            try:
                return await extractor.extract(processed)
            except Exception as exc:
                log.warning("extractor_failed", extractor=type(extractor).__name__, error=str(exc))
                return None

        raw_results = await asyncio.gather(*[_safe_extract(e) for e in matched])
        valid = [r for r in raw_results if r is not None]
        merged = _merge_results(valid) if valid else ExtractionResult(
            summary="", facts=[], entities=[], tags=[]
        )

        # 5. Store
        ingestion_id = str(uuid.uuid4())
        await self._store.save(
            ingestion_id=ingestion_id,
            processed=processed,
            extraction=merged,
        )

        # 6. Sink
        await emit("ingestion.saving")
        await self._sink.push(ingestion_id=ingestion_id, facts=merged.facts)

        return IngestionResult(
            ingestion_id=ingestion_id,
            content_type=content_type,
            source_url=request.url,
            summary=merged.summary,
            facts_count=len(merged.facts),
            entities_count=len(merged.entities),
            tags=merged.tags,
        )
