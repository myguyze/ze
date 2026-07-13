from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from ze_ingestion.extractors.llm import LLMExtractor
from ze_ingestion.types import ContentType, ProcessedContent


@pytest.fixture
def content() -> ProcessedContent:
    return ProcessedContent(
        content_type=ContentType.WEB_PAGE,
        source_url="https://example.com",
        text="Python is a programming language created by Guido van Rossum in 1991.",
    )


@pytest.fixture
def client() -> AsyncMock:
    return AsyncMock()


def _extractor(client: AsyncMock) -> LLMExtractor:
    return LLMExtractor(llm_client=client, model="test-model")


async def test_successful_extraction(
    client: AsyncMock, content: ProcessedContent
) -> None:
    client.complete.return_value = json.dumps(
        {
            "summary": "Python overview.",
            "facts": [
                "Python was created in 1991.",
                "Guido van Rossum is the creator.",
            ],
            "entities": ["Python", "Guido van Rossum"],
            "tags": ["programming", "language"],
        }
    )
    result = await _extractor(client).extract(content)
    assert result.summary == "Python overview."
    assert "Python was created in 1991." in result.facts
    assert "Guido van Rossum" in result.entities
    assert "programming" in result.tags


async def test_content_types_is_empty_meaning_all(client: AsyncMock) -> None:
    ext = _extractor(client)
    assert ext.content_types == []


async def test_llm_failure_returns_empty_result(
    client: AsyncMock, content: ProcessedContent
) -> None:
    client.complete.side_effect = RuntimeError("LLM unavailable")
    result = await _extractor(client).extract(content)
    assert result.summary == ""
    assert result.facts == []
    assert result.entities == []
    assert result.tags == []


async def test_malformed_json_returns_empty_result(
    client: AsyncMock, content: ProcessedContent
) -> None:
    client.complete.return_value = "not valid json {"
    result = await _extractor(client).extract(content)
    assert result.summary == ""
    assert result.facts == []


async def test_partial_json_uses_defaults(
    client: AsyncMock, content: ProcessedContent
) -> None:
    client.complete.return_value = json.dumps(
        {"summary": "Partial.", "facts": ["One fact."]}
    )
    result = await _extractor(client).extract(content)
    assert result.summary == "Partial."
    assert result.facts == ["One fact."]
    assert result.entities == []
    assert result.tags == []


async def test_truncates_long_content(client: AsyncMock) -> None:
    long_content = ProcessedContent(
        content_type=ContentType.WEB_PAGE,
        source_url=None,
        text="x" * 20_000,
    )
    client.complete.return_value = json.dumps(
        {"summary": "ok", "facts": [], "entities": [], "tags": []}
    )
    await _extractor(client).extract(long_content)
    call_args = client.complete.call_args
    sent_text = call_args.kwargs["messages"][0]["content"]
    assert len(sent_text) < 13_000
