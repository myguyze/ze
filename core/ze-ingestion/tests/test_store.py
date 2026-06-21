from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_ingestion.store import IngestionStore
from ze_ingestion.types import ContentType, ExtractionResult, ProcessedContent


@pytest.fixture
def pool() -> MagicMock:
    conn = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.acquire.return_value = ctx
    return pool


@pytest.fixture
def processed() -> ProcessedContent:
    return ProcessedContent(
        content_type=ContentType.WEB_PAGE,
        source_url="https://example.com/article",
        text="Some article text.",
        metadata={"title": "Article"},
    )


@pytest.fixture
def extraction() -> ExtractionResult:
    return ExtractionResult(
        summary="A summary.",
        facts=["Fact one.", "Fact two."],
        entities=["Entity A"],
        tags=["tech", "news"],
        metadata={"word_count": 3},
    )


async def test_save_executes_insert(
    pool: MagicMock,
    processed: ProcessedContent,
    extraction: ExtractionResult,
) -> None:
    store = IngestionStore(pool)
    await store.save(ingestion_id="test-id-123", processed=processed, extraction=extraction)

    conn = pool.acquire.return_value.__aenter__.return_value
    conn.execute.assert_called_once()
    call_args = conn.execute.call_args.args
    assert "INSERT INTO ingested_content" in call_args[0]
    assert call_args[1] == "test-id-123"
    assert call_args[2] == "https://example.com/article"
    assert call_args[3] == ContentType.WEB_PAGE.value
    assert call_args[4] == "Some article text."
    assert call_args[5] == "A summary."
    assert json.loads(call_args[6]) == ["Fact one.", "Fact two."]
    assert json.loads(call_args[7]) == ["Entity A"]
    assert json.loads(call_args[8]) == ["tech", "news"]


async def test_save_merges_processed_and_extraction_metadata(
    pool: MagicMock,
    processed: ProcessedContent,
    extraction: ExtractionResult,
) -> None:
    store = IngestionStore(pool)
    await store.save(ingestion_id="x", processed=processed, extraction=extraction)

    conn = pool.acquire.return_value.__aenter__.return_value
    metadata_arg = conn.execute.call_args.args[9]
    merged = json.loads(metadata_arg)
    assert merged["title"] == "Article"
    assert merged["word_count"] == 3
