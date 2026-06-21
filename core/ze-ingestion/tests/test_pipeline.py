from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_ingestion.classifier import ContentClassifier
from ze_ingestion.errors import UnsupportedContentError
from ze_ingestion.pipeline import IngestionPipeline, _merge_results
from ze_ingestion.types import (
    ContentType,
    ExtractionResult,
    IngestionRequest,
    ProcessedContent,
    RawContent,
)


# ---------------------------------------------------------------------------
# _merge_results unit tests
# ---------------------------------------------------------------------------

def test_merge_joins_summaries_with_double_newline() -> None:
    results = [
        ExtractionResult(summary="First.", facts=[], entities=[], tags=[]),
        ExtractionResult(summary="Second.", facts=[], entities=[], tags=[]),
    ]
    merged = _merge_results(results)
    assert merged.summary == "First.\n\nSecond."


def test_merge_skips_empty_summaries() -> None:
    results = [
        ExtractionResult(summary="", facts=[], entities=[], tags=[]),
        ExtractionResult(summary="Real.", facts=[], entities=[], tags=[]),
    ]
    merged = _merge_results(results)
    assert merged.summary == "Real."


def test_merge_deduplicates_facts() -> None:
    results = [
        ExtractionResult(summary="", facts=["A", "B"], entities=[], tags=[]),
        ExtractionResult(summary="", facts=["B", "C"], entities=[], tags=[]),
    ]
    merged = _merge_results(results)
    assert merged.facts == ["A", "B", "C"]


def test_merge_deduplicates_entities_and_tags() -> None:
    results = [
        ExtractionResult(summary="", facts=[], entities=["X", "Y"], tags=["t1"]),
        ExtractionResult(summary="", facts=[], entities=["Y", "Z"], tags=["t1", "t2"]),
    ]
    merged = _merge_results(results)
    assert merged.entities == ["X", "Y", "Z"]
    assert merged.tags == ["t1", "t2"]


def test_merge_metadata_later_overwrites_earlier() -> None:
    results = [
        ExtractionResult(summary="", facts=[], entities=[], tags=[], metadata={"a": 1, "b": 2}),
        ExtractionResult(summary="", facts=[], entities=[], tags=[], metadata={"b": 99, "c": 3}),
    ]
    merged = _merge_results(results)
    assert merged.metadata == {"a": 1, "b": 99, "c": 3}


# ---------------------------------------------------------------------------
# Pipeline fixtures
# ---------------------------------------------------------------------------

def _make_fetcher(content_type: ContentType = ContentType.WEB_PAGE) -> MagicMock:
    fetcher = MagicMock()
    fetcher.url_patterns = [r".*"]
    fetcher.fetch = AsyncMock(return_value=RawContent(
        content_type=content_type,
        source_url="https://example.com",
        data=b"<html><body>Hello</body></html>",
        mime_type="text/html",
    ))
    return fetcher


def _make_processor(content_type: ContentType = ContentType.WEB_PAGE) -> MagicMock:
    proc = MagicMock()
    proc.content_types = [content_type, ContentType.UNKNOWN]
    proc.process = AsyncMock(return_value=ProcessedContent(
        content_type=content_type,
        source_url="https://example.com",
        text="Hello",
    ))
    return proc


def _make_extractor(
    summary: str = "A summary.",
    content_types: list[ContentType] | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    ext = MagicMock()
    ext.content_types = content_types if content_types is not None else []
    if side_effect:
        ext.extract = AsyncMock(side_effect=side_effect)
    else:
        ext.extract = AsyncMock(return_value=ExtractionResult(
            summary=summary,
            facts=["fact"],
            entities=["entity"],
            tags=["tag"],
        ))
    return ext


def _make_store() -> AsyncMock:
    return AsyncMock()


def _make_sink() -> AsyncMock:
    return AsyncMock()


def _pipeline(
    fetcher: MagicMock | None = None,
    processor: MagicMock | None = None,
    extractor: MagicMock | None = None,
    store: AsyncMock | None = None,
    sink: AsyncMock | None = None,
) -> IngestionPipeline:
    return IngestionPipeline(
        classifier=ContentClassifier(),
        fetchers=[fetcher or _make_fetcher()],
        processors=[processor or _make_processor()],
        extractors=[extractor or _make_extractor()],
        store=store or _make_store(),
        memory_sink=sink or _make_sink(),
    )


# ---------------------------------------------------------------------------
# Pipeline.ingest — URL path
# ---------------------------------------------------------------------------

async def test_ingest_url_returns_result() -> None:
    pipeline = _pipeline()
    result = await pipeline.ingest(IngestionRequest(url="https://example.com/article"))
    assert result.content_type == ContentType.WEB_PAGE
    assert result.source_url == "https://example.com/article"
    assert result.summary == "A summary."
    assert result.facts_count == 1
    assert result.tags == ["tag"]


async def test_ingest_url_calls_store_and_sink() -> None:
    store = _make_store()
    sink = _make_sink()
    pipeline = _pipeline(store=store, sink=sink)
    await pipeline.ingest(IngestionRequest(url="https://example.com"))
    store.save.assert_called_once()
    sink.push.assert_called_once()


async def test_ingest_url_sink_receives_ingestion_id_and_facts() -> None:
    sink = _make_sink()
    pipeline = _pipeline(sink=sink)
    await pipeline.ingest(IngestionRequest(url="https://example.com"))
    call_kwargs = sink.push.call_args.kwargs
    assert "ingestion_id" in call_kwargs
    assert call_kwargs["facts"] == ["fact"]


# ---------------------------------------------------------------------------
# Pipeline.ingest — file_bytes path (no fetch)
# ---------------------------------------------------------------------------

async def test_ingest_file_bytes_skips_fetch() -> None:
    fetcher = _make_fetcher()
    pipeline = _pipeline(fetcher=fetcher)
    await pipeline.ingest(IngestionRequest(
        file_bytes=b"Hello plain text",
        mime_type="text/plain",
    ))
    fetcher.fetch.assert_not_called()


async def test_ingest_file_bytes_source_url_is_none() -> None:
    pipeline = _pipeline()
    result = await pipeline.ingest(IngestionRequest(file_bytes=b"text", mime_type="text/plain"))
    assert result.source_url is None


# ---------------------------------------------------------------------------
# Reporter emissions
# ---------------------------------------------------------------------------

async def test_reporter_receives_classifying_and_extracting_keys() -> None:
    reporter = AsyncMock()
    pipeline = _pipeline()
    await pipeline.ingest(IngestionRequest(url="https://example.com"), reporter=reporter)
    emitted = [call.args[0] for call in reporter.emit.call_args_list]
    assert "ingestion.classifying" in emitted
    assert "ingestion.fetching" in emitted
    assert "ingestion.extracting" in emitted
    assert "ingestion.saving" in emitted


async def test_no_reporter_does_not_raise() -> None:
    pipeline = _pipeline()
    await pipeline.ingest(IngestionRequest(url="https://example.com"), reporter=None)


# ---------------------------------------------------------------------------
# Extractor resilience
# ---------------------------------------------------------------------------

async def test_failing_extractor_skipped_others_still_run() -> None:
    failing = _make_extractor(side_effect=RuntimeError("boom"))
    working = _make_extractor(summary="ok")
    pipeline = _pipeline(extractor=None)
    pipeline._extractors = [failing, working]
    result = await pipeline.ingest(IngestionRequest(url="https://example.com"))
    assert result.summary == "ok"


async def test_all_extractors_run_for_matching_content_type() -> None:
    ext1 = _make_extractor(summary="First", content_types=[ContentType.WEB_PAGE])
    ext2 = _make_extractor(summary="Second", content_types=[])
    pipeline = _pipeline()
    pipeline._extractors = [ext1, ext2]
    result = await pipeline.ingest(IngestionRequest(url="https://example.com"))
    assert "First" in result.summary
    assert "Second" in result.summary


# ---------------------------------------------------------------------------
# No fetcher match
# ---------------------------------------------------------------------------

async def test_no_matching_fetcher_raises() -> None:
    fetcher = _make_fetcher()
    fetcher.url_patterns = [r"^https://specific\.com"]
    pipeline = _pipeline(fetcher=fetcher)
    with pytest.raises(UnsupportedContentError):
        await pipeline.ingest(IngestionRequest(url="https://other.com/page"))


# ---------------------------------------------------------------------------
# No processor match
# ---------------------------------------------------------------------------

async def test_no_matching_processor_raises() -> None:
    processor = _make_processor()
    processor.content_types = [ContentType.VIDEO]
    pipeline = _pipeline(processor=processor)
    # URL will classify as WEB_PAGE, no processor for that type
    pipeline._processors = [processor]
    with pytest.raises(UnsupportedContentError):
        await pipeline.ingest(IngestionRequest(url="https://example.com"))
