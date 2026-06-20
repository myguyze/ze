from __future__ import annotations

from ze_ingestion.errors import FetchError
from ze_ingestion.types import ContentType, RawContent
from ze_yt.client import YtDlpClient

_VIDEO_URL_PATTERNS = [
    r"youtu(?:be\.com/watch|\.be/)",
    r"instagram\.com/(?:reel|p)/",
    r"tiktok\.com/",
    r"vimeo\.com/",
    r"twitter\.com/.+/status",
    r"x\.com/.+/status",
]


class YtDlpFetcher:
    url_patterns: list[str] = _VIDEO_URL_PATTERNS

    def __init__(self, client: YtDlpClient | None = None) -> None:
        self._client = client or YtDlpClient()

    async def fetch(self, url: str) -> RawContent:
        try:
            data = await self._client.download_audio(url)
        except Exception as exc:
            raise FetchError(f"yt-dlp fetch failed for {url}: {exc}") from exc
        return RawContent(
            content_type=ContentType.AUDIO,
            source_url=url,
            data=data,
            mime_type="audio/mpeg",
        )
