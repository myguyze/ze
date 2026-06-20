from __future__ import annotations

from ze_ingestion.types import ContentType, ProcessedContent, RawContent


class HtmlProcessor:
    content_types: list[ContentType] = [ContentType.WEB_PAGE]

    async def process(self, raw: RawContent) -> ProcessedContent:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw.data, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        text = soup.get_text(separator="\n", strip=True)

        return ProcessedContent(
            content_type=raw.content_type,
            source_url=raw.source_url,
            text=text,
            metadata={"title": title} if title else {},
        )
