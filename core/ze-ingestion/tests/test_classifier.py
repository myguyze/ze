from __future__ import annotations

import pytest

from ze_ingestion.classifier import ContentClassifier
from ze_ingestion.types import ContentType


@pytest.fixture
def clf() -> ContentClassifier:
    return ContentClassifier()


# --- classify_url ---

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc123", ContentType.VIDEO),
    ("https://youtu.be/abc123", ContentType.VIDEO),
    ("https://www.instagram.com/reel/abc123/", ContentType.VIDEO),
    ("https://www.instagram.com/p/abc123/", ContentType.VIDEO),
    ("https://www.tiktok.com/@user/video/123", ContentType.VIDEO),
    ("https://vimeo.com/123456789", ContentType.VIDEO),
    ("https://twitter.com/user/status/123", ContentType.VIDEO),
    ("https://x.com/user/status/123", ContentType.VIDEO),
    ("https://example.com/doc.pdf", ContentType.PDF),
    ("https://example.com/doc.pdf?token=abc", ContentType.PDF),
    ("https://example.com/song.mp3", ContentType.AUDIO),
    ("https://example.com/clip.ogg", ContentType.AUDIO),
    ("https://example.com/clip.wav", ContentType.AUDIO),
    ("https://example.com/clip.m4a", ContentType.AUDIO),
    ("https://example.com/photo.png", ContentType.IMAGE),
    ("https://example.com/photo.jpg", ContentType.IMAGE),
    ("https://example.com/photo.jpeg", ContentType.IMAGE),
    ("https://example.com/photo.gif", ContentType.IMAGE),
    ("https://example.com/photo.webp", ContentType.IMAGE),
])
def test_classify_url_known_patterns(clf: ContentClassifier, url: str, expected: ContentType) -> None:
    assert clf.classify_url(url) == expected


def test_classify_url_generic_returns_none(clf: ContentClassifier) -> None:
    assert clf.classify_url("https://example.com/article") is None


# --- classify_mime ---

@pytest.mark.parametrize("mime,expected", [
    ("application/pdf", ContentType.PDF),
    ("text/html", ContentType.WEB_PAGE),
    ("text/html; charset=utf-8", ContentType.WEB_PAGE),
    ("text/plain", ContentType.PLAIN_TEXT),
    ("image/png", ContentType.IMAGE),
    ("image/jpeg", ContentType.IMAGE),
    ("image/gif", ContentType.IMAGE),
    ("image/webp", ContentType.IMAGE),
    ("audio/mpeg", ContentType.AUDIO),
    ("audio/ogg", ContentType.AUDIO),
    ("audio/wav", ContentType.AUDIO),
    ("audio/mp4", ContentType.AUDIO),
    ("video/mp4", ContentType.VIDEO),
    ("video/webm", ContentType.VIDEO),
])
def test_classify_mime_known_types(clf: ContentClassifier, mime: str, expected: ContentType) -> None:
    assert clf.classify_mime(mime) == expected


def test_classify_mime_unknown_returns_none(clf: ContentClassifier) -> None:
    assert clf.classify_mime("application/octet-stream") is None


# --- classify_bytes ---

@pytest.mark.parametrize("magic,expected", [
    (b"%PDF-1.4 ...", ContentType.PDF),
    (b"ID3\x03\x00...", ContentType.AUDIO),
    (b"\xff\xfb\x90\x00...", ContentType.AUDIO),
    (b"\x89PNG\r\n\x1a\n", ContentType.IMAGE),
    (b"\xff\xd8\xff\xe0...", ContentType.IMAGE),
    (b"GIF89a...", ContentType.IMAGE),
    (b"<html><head>", ContentType.WEB_PAGE),
    (b"<!DOCTYPE html>", ContentType.WEB_PAGE),
])
def test_classify_bytes_magic(clf: ContentClassifier, magic: bytes, expected: ContentType) -> None:
    assert clf.classify_bytes(magic) == expected


def test_classify_bytes_unknown_returns_none(clf: ContentClassifier) -> None:
    assert clf.classify_bytes(b"\x00\x01\x02\x03") is None


# --- classify (priority order) ---

def test_classify_url_beats_mime(clf: ContentClassifier) -> None:
    # URL says VIDEO (YouTube), MIME says PDF — URL wins
    result = clf.classify(
        url="https://youtu.be/abc",
        mime_type="application/pdf",
    )
    assert result == ContentType.VIDEO


def test_classify_mime_beats_bytes(clf: ContentClassifier) -> None:
    # MIME says PDF, bytes say HTML — MIME wins
    result = clf.classify(
        url=None,
        mime_type="application/pdf",
        data=b"<html>",
    )
    assert result == ContentType.PDF


def test_classify_falls_back_to_bytes(clf: ContentClassifier) -> None:
    result = clf.classify(
        url="https://example.com/data",
        mime_type=None,
        data=b"%PDF-1.4",
    )
    assert result == ContentType.PDF


def test_classify_returns_unknown_when_no_signal(clf: ContentClassifier) -> None:
    result = clf.classify(url="https://example.com/data", mime_type=None, data=None)
    assert result == ContentType.UNKNOWN


def test_classify_all_none(clf: ContentClassifier) -> None:
    assert clf.classify() == ContentType.UNKNOWN
