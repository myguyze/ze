from __future__ import annotations

from ze_ingestion.errors import FetchError
from ze_ingestion.types import ContentType, RawContent


class BrowserFetcher:
    """Fetches JS-heavy pages via the ze-browser sidecar."""

    url_patterns: list[str] = []

    def __init__(self, browser_client: object) -> None:
        self._client = browser_client

    async def fetch(self, url: str) -> RawContent:
        try:
            result = await self._client.extract(url)  # type: ignore[attr-defined]
        except Exception as exc:
            raise FetchError(f"Browser fetch failed for {url}: {exc}") from exc
        html = getattr(result, "html", "") or getattr(result, "text", "") or ""
        return RawContent(
            content_type=ContentType.WEB_PAGE,
            source_url=url,
            data=html.encode(),
            mime_type="text/html",
        )
