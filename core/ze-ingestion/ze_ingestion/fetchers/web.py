from __future__ import annotations

import httpx

from ze_ingestion.errors import FetchError
from ze_ingestion.types import ContentType, RawContent

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Ze-Ingestion/1.0)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class WebFetcher:
    url_patterns: list[str] = [".*"]

    async def fetch(self, url: str) -> RawContent:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers=_DEFAULT_HEADERS,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise FetchError(f"HTTP error fetching {url}: {exc}") from exc

        content_type_hdr = resp.headers.get("content-type", "text/html")
        mime = content_type_hdr.split(";")[0].strip()
        return RawContent(
            content_type=ContentType.UNKNOWN,
            source_url=url,
            data=resp.content,
            mime_type=mime,
        )
