from __future__ import annotations

import re

from ze_ingestion.types import ContentType

_URL_PATTERNS: list[tuple[re.Pattern, ContentType]] = [
    (re.compile(r"youtu(?:be\.com/watch|\.be/)", re.I), ContentType.VIDEO),
    (re.compile(r"instagram\.com/(?:reel|p)/", re.I), ContentType.VIDEO),
    (re.compile(r"tiktok\.com/", re.I), ContentType.VIDEO),
    (re.compile(r"vimeo\.com/", re.I), ContentType.VIDEO),
    (re.compile(r"twitter\.com/.+/status|x\.com/.+/status", re.I), ContentType.VIDEO),
    (re.compile(r"\.pdf(?:\?|$)", re.I), ContentType.PDF),
    (re.compile(r"\.mp3(?:\?|$)|\.ogg(?:\?|$)|\.wav(?:\?|$)|\.m4a(?:\?|$)", re.I), ContentType.AUDIO),
    (re.compile(r"\.png(?:\?|$)|\.jpe?g(?:\?|$)|\.gif(?:\?|$)|\.webp(?:\?|$)", re.I), ContentType.IMAGE),
]

_MIME_MAP: dict[str, ContentType] = {
    "application/pdf": ContentType.PDF,
    "text/html": ContentType.WEB_PAGE,
    "text/plain": ContentType.PLAIN_TEXT,
    "image/png": ContentType.IMAGE,
    "image/jpeg": ContentType.IMAGE,
    "image/gif": ContentType.IMAGE,
    "image/webp": ContentType.IMAGE,
    "audio/mpeg": ContentType.AUDIO,
    "audio/ogg": ContentType.AUDIO,
    "audio/wav": ContentType.AUDIO,
    "audio/mp4": ContentType.AUDIO,
    "video/mp4": ContentType.VIDEO,
    "video/webm": ContentType.VIDEO,
}

_MAGIC: list[tuple[bytes, ContentType]] = [
    (b"%PDF-", ContentType.PDF),
    (b"ID3", ContentType.AUDIO),
    (b"\xff\xfb", ContentType.AUDIO),
    (b"\x00\x00\x00\x20ftyp", ContentType.VIDEO),
    (b"\x00\x00\x00\x18ftyp", ContentType.VIDEO),
    (b"\x89PNG", ContentType.IMAGE),
    (b"\xff\xd8\xff", ContentType.IMAGE),
    (b"GIF8", ContentType.IMAGE),
    (b"RIFF", ContentType.AUDIO),
    (b"<html", ContentType.WEB_PAGE),
    (b"<!DOCTYPE", ContentType.WEB_PAGE),
]


class ContentClassifier:
    def classify_url(self, url: str) -> ContentType | None:
        for pattern, ct in _URL_PATTERNS:
            if pattern.search(url):
                return ct
        return None

    def classify_mime(self, mime: str) -> ContentType | None:
        base = mime.split(";")[0].strip().lower()
        return _MIME_MAP.get(base)

    def classify_bytes(self, data: bytes) -> ContentType | None:
        snippet = data[:512]
        snippet_lower = snippet.lower()
        for magic, ct in _MAGIC:
            if snippet.startswith(magic) or magic.lower() in snippet_lower[:16]:
                return ct
        return None

    def classify(
        self,
        url: str | None = None,
        mime_type: str | None = None,
        data: bytes | None = None,
    ) -> ContentType:
        if url:
            ct = self.classify_url(url)
            if ct:
                return ct
        if mime_type:
            ct = self.classify_mime(mime_type)
            if ct:
                return ct
        if data:
            ct = self.classify_bytes(data)
            if ct:
                return ct
        return ContentType.UNKNOWN
