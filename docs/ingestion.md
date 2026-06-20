# Content Ingestion

Ze can ingest arbitrary external content — web pages, PDFs, YouTube videos, audio files, images, and plain text — and store the extracted knowledge in its memory. This doc covers how the pipeline works, how plugins extend it, and how the `ze-yt` integration adds video support.

---

## Overview

Ingestion turns unstructured external content into structured knowledge:

```
URL / file / text
       │
       ▼
 ContentClassifier          ← URL pattern → MIME hint → magic bytes
       │
       ▼
    Fetcher                 ← WebFetcher | BrowserFetcher | YtDlpFetcher | plugin fetcher
       │
       ▼
   Processor               ← HTML → PDF → Audio (Whisper) → Image (vision) → Text
       │
       ▼
 Extractors (parallel)     ← LLMExtractor + any plugin extractors
       │
       ▼
IngestionStore             ← archives raw text + extraction in `ingested_content`
       │
       ▼
  MemorySink               ← proposes facts to ze-memory
```

Every stage emits a progress key so the user sees live status during long operations (video transcription, LLM extraction).

---

## Content Types

| `ContentType` | Typical source |
|---|---|
| `web_page` | Any HTTP URL returning HTML |
| `pdf` | `.pdf` URL or uploaded PDF file |
| `audio` | `.mp3`/`.ogg`/`.wav` URL or uploaded audio |
| `video` | YouTube, Instagram Reels, TikTok, Vimeo (via `ze-yt`) |
| `image` | `.png`/`.jpg`/`.webp` URL or uploaded image |
| `plain_text` | Raw text submitted by user |
| `document` | Word docs, spreadsheets (treated as plain text) |
| `unknown` | Fallback — `TextProcessor` handles as UTF-8 |

---

## Pipeline Stages

### 1. Classify

`ContentClassifier` determines the content type in priority order:

1. URL pattern matching — well-known domains (YouTube → `video`, `.pdf` URLs → `pdf`, etc.)
2. MIME type hint — if the caller provides `mime_type`
3. Magic bytes sniff — first 512 bytes (`%PDF-` → `pdf`, `ID3` → `audio`, etc.)
4. Fallback — `unknown`

### 2. Fetch

For URL inputs, the pipeline walks the fetcher list in order; the first fetcher whose `url_patterns` match the URL is used. The fallback is always `WebFetcher`.

For file inputs, the bytes are wrapped directly in `RawContent` — no network call.

### 3. Process

The first `Processor` whose `content_types` includes the classified type converts `RawContent` to `ProcessedContent` (plain text + metadata).

| Processor | What it does |
|---|---|
| `HtmlProcessor` | BeautifulSoup parse; strips nav/footer/scripts; extracts title |
| `PdfProcessor` | `pypdf` page extraction; counts pages |
| `AudioProcessor` | OpenRouter Whisper transcription via `LLMClient` |
| `ImageProcessor` | Vision LLM description (Gemini Flash 1.5) via `LLMClient` |
| `TextProcessor` | UTF-8 passthrough; handles `plain_text`, `document`, `unknown` |

### 4. Extract

All `Extractor`s whose `content_types` includes the classified type (or is empty, meaning "all types") run in parallel via `asyncio.gather`. Results are merged:

- `summary` — non-empty summaries joined with `\n\n`
- `facts`, `entities`, `tags` — union, deduplicated by exact string match
- `metadata` — dict merge (later extractor keys overwrite on conflict)

If an extractor raises, its result is skipped and the error is logged. At least `LLMExtractor` always runs, so the merge never produces an empty result.

### 5. Store

`IngestionStore` writes to `ingested_content` — the authoritative archive. The raw processed text, summary, facts, entities, tags, and metadata are all stored.

### 6. Sink

`MemorySink` calls `ze-memory`'s `propose_facts()` with each extracted fact string. Facts flow into Ze's long-term memory and become available for retrieval in future conversations.

---

## Plugin Extension Points

### Registering extractors

Override `ingestion_extractors()` on your `ZePlugin` subclass:

```python
from ze_ingestion.extractors import Extractor
from ze_ingestion.types import ContentType, ExtractionResult, ProcessedContent


class TransactionExtractor:
    content_types = [ContentType.PDF]  # only runs on PDFs

    async def extract(self, content: ProcessedContent) -> ExtractionResult:
        transactions = _parse_transactions(content.text)
        return ExtractionResult(
            summary=f"Found {len(transactions)} transactions.",
            facts=[f"Transaction: {t}" for t in transactions],
            entities=[],
            tags=["finance", "transactions"],
        )


class FinancePlugin(ZePlugin):
    def ingestion_extractors(self) -> list:
        return [TransactionExtractor()]
```

Set `content_types = []` to match all content types (same as `LLMExtractor`).

### Registering fetchers

Override `ingestion_fetchers()` to add fetchers for custom URL schemes:

```python
from ze_ingestion.fetchers import Fetcher
from ze_ingestion.types import ContentType, RawContent


class NotionFetcher:
    url_patterns = [r"notion\.so/"]

    async def fetch(self, url: str) -> RawContent:
        text = await _notion_api_export(url)
        return RawContent(
            content_type=ContentType.PLAIN_TEXT,
            source_url=url,
            data=text.encode(),
            mime_type="text/plain",
        )


class MyPlugin(ZePlugin):
    def ingestion_fetchers(self) -> list:
        return [NotionFetcher()]
```

Plugin fetchers are placed after `YtDlpFetcher` (if installed) but before `BrowserFetcher` and `WebFetcher`.

---

## `IngestionAgent`

`IngestionAgent` routes user requests such as "save this link", "learn from this PDF", "watch this video and remember it". It exposes two tools:

| Tool | When used |
|---|---|
| `ingest_url` | Any URL the user provides |
| `ingest_text` | Raw text or pre-extracted content |

Both tools drive the full `IngestionPipeline` and return a summary of what was ingested (content type, fact count, tags).

Progress messages are emitted at each stage, so the user sees live feedback during long steps like video transcription.

---

## REST Endpoint

```
POST /api/ingest
Content-Type: multipart/form-data

Fields:
  url    (string, optional)  URL to ingest
  file   (file, optional)    Uploaded file
  label  (string, optional)  User-supplied title

Response 200:
{
  "ingestion_id": "...",
  "content_type": "pdf",
  "summary": "...",
  "facts_count": 12,
  "tags": ["finance", "investment"]
}

422 if neither or both of url/file are provided.
```

---

## `ze-yt` — Video Integration

`integrations/ze-yt` adds YouTube, Instagram, TikTok, Vimeo, and Twitter/X video support.

`YtDlpFetcher` matches video URLs, runs `yt-dlp --extract-audio --audio-format mp3` as a subprocess, and returns the MP3 bytes as `RawContent(content_type=AUDIO)`. `AudioProcessor` then transcribes via OpenRouter Whisper.

`yt-dlp` must be installed as a system binary or via `uv tool`. If it is not installed or `ze-yt` is not in the dependency tree, video URLs fall back to `WebFetcher` (which will return the page HTML rather than the video audio).

---

## Database

`ze_ingestion` owns the `ingested_content` table (migration branch `zi`, first revision `zi001`):

```sql
CREATE TABLE ingested_content (
    id           TEXT        PRIMARY KEY,
    source_url   TEXT,
    content_type TEXT        NOT NULL,
    raw_text     TEXT        NOT NULL,
    summary      TEXT,
    facts        JSONB       NOT NULL DEFAULT '[]',
    entities     JSONB       NOT NULL DEFAULT '[]',
    tags         JSONB       NOT NULL DEFAULT '[]',
    metadata     JSONB       NOT NULL DEFAULT '{}',
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`ingested_content` is the authoritative archive of everything ever ingested. `ze-memory` holds only the distilled facts — the full processed text lives here.

---

## Data Portability

Ingested content is part of Ze's exportable data. Domain plugins that own ingestion-derived data (e.g. extracted transactions in `ze-finance`) should declare their tables as `DataDomain` instances via `ZePlugin.data_domains()`. See [data-portability.md](data-portability.md) for the export/import/delete contract.
