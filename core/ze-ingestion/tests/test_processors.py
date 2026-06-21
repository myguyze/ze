from __future__ import annotations

import pytest

from ze_ingestion.processors.html import HtmlProcessor
from ze_ingestion.processors.text import TextProcessor
from ze_ingestion.types import ContentType, RawContent


def _raw(data: bytes, content_type: ContentType = ContentType.WEB_PAGE, mime: str = "text/html") -> RawContent:
    return RawContent(content_type=content_type, source_url="https://example.com", data=data, mime_type=mime)


# --- TextProcessor ---

class TestTextProcessor:
    @pytest.fixture
    def proc(self) -> TextProcessor:
        return TextProcessor()

    async def test_returns_decoded_text(self, proc: TextProcessor) -> None:
        raw = _raw(b"Hello world", ContentType.PLAIN_TEXT, "text/plain")
        result = await proc.process(raw)
        assert result.text == "Hello world"
        assert result.content_type == ContentType.PLAIN_TEXT
        assert result.source_url == "https://example.com"

    async def test_handles_invalid_utf8_with_replacement(self, proc: TextProcessor) -> None:
        raw = _raw(b"Hello \xff world", ContentType.PLAIN_TEXT, "text/plain")
        result = await proc.process(raw)
        assert "Hello" in result.text
        assert "�" in result.text

    async def test_handles_unknown_content_type(self, proc: TextProcessor) -> None:
        raw = _raw(b"some bytes", ContentType.UNKNOWN, "application/octet-stream")
        result = await proc.process(raw)
        assert result.text == "some bytes"

    async def test_content_types_includes_unknown(self, proc: TextProcessor) -> None:
        assert ContentType.UNKNOWN in proc.content_types
        assert ContentType.PLAIN_TEXT in proc.content_types


# --- HtmlProcessor ---

class TestHtmlProcessor:
    @pytest.fixture
    def proc(self) -> HtmlProcessor:
        return HtmlProcessor()

    async def test_extracts_body_text(self, proc: HtmlProcessor) -> None:
        html = b"<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        result = await proc.process(_raw(html))
        assert "Hello world" in result.text

    async def test_strips_script_tags(self, proc: HtmlProcessor) -> None:
        html = b"<html><body><p>Content</p><script>alert('xss')</script></body></html>"
        result = await proc.process(_raw(html))
        assert "alert" not in result.text
        assert "Content" in result.text

    async def test_strips_style_tags(self, proc: HtmlProcessor) -> None:
        html = b"<html><body><style>body{color:red}</style><p>Text</p></body></html>"
        result = await proc.process(_raw(html))
        assert "color" not in result.text
        assert "Text" in result.text

    async def test_extracts_title_into_metadata(self, proc: HtmlProcessor) -> None:
        html = b"<html><head><title>My Article</title></head><body><p>Body</p></body></html>"
        result = await proc.process(_raw(html))
        assert result.metadata.get("title") == "My Article"

    async def test_no_title_gives_empty_metadata(self, proc: HtmlProcessor) -> None:
        html = b"<html><body><p>Body</p></body></html>"
        result = await proc.process(_raw(html))
        assert "title" not in result.metadata

    async def test_preserves_source_url(self, proc: HtmlProcessor) -> None:
        result = await proc.process(_raw(b"<html><body>hi</body></html>"))
        assert result.source_url == "https://example.com"

    async def test_content_types_includes_web_page(self, proc: HtmlProcessor) -> None:
        assert ContentType.WEB_PAGE in proc.content_types
