# ze-ingestion — Spec

> **Package:** `core/ze-ingestion`
> **Phase:** 69
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ContentType` enum + `IngestionRequest` types | ✅ Done |
| `ContentClassifier` | ✅ Done |
| `Fetcher` protocol + `WebFetcher` + `BrowserFetcher` | ✅ Done |
| `Processor` protocol + PDF / HTML / Audio / Image / Text processors | ✅ Done |
| `Extractor` protocol + default `LLMExtractor` | ✅ Done |
| `IngestionPipeline` (run-all-merge) | ✅ Done |
| `IngestionStore` + migration (`zi001`) | ✅ Done |
| `MemorySink` | ✅ Done |
| `IngestionAgent` | ✅ Done |
| `ZePlugin.ingestion_extractors()` hook | ✅ Done |
| `ZePlugin.ingestion_fetchers()` hook | ✅ Done |
| `POST /api/ingest` route | ✅ Done |
| `integrations/ze-yt/` — `YtDlpFetcher` | ✅ Done |
| `ze-finance` `FinanceIngestionExtractor` | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

`ze-ingestion` is a core pipeline that accepts arbitrary external content — a URL, a
file, raw text — classifies it, fetches and processes it into plain text, runs all
registered extractors to pull out structured knowledge, archives the result, and sinks
facts into `ze-memory`.

The pipeline is designed to be fully generic. Domain plugins extend it by registering
`Extractor` implementations keyed to content types they understand (e.g. a finance
plugin registers a `TransactionExtractor` for PDF bank statements). The default
`LLMExtractor` shipped in `ze-ingestion` handles everything else.

When multiple extractors match a content type, all are run in parallel and their
results are merged. No extractor has veto power over another.

---

## Responsibilities

- Define the `ContentType` enum and all pipeline protocols (`Fetcher`, `Processor`, `Extractor`)
- Implement `ContentClassifier` (URL pattern + MIME + magic bytes)
- Implement built-in fetchers: `WebFetcher` (httpx), `BrowserFetcher` (via `ze-browser`)
- Implement built-in processors: `HtmlProcessor`, `PdfProcessor`, `AudioProcessor`,
  `ImageProcessor`, `TextProcessor`
- Implement default `LLMExtractor` (summary, facts, entities, tags via LLM)
- Implement `IngestionPipeline` (orchestrates classify → fetch → process → extract → store → sink)
- Own `IngestionStore` and the `ingested_content` database table
- Implement `MemorySink` (pushes extracted facts into `ze-memory`)
- Ship `IngestionAgent` (receives ingestion requests from the orchestration graph)
- Extend `ZePlugin` with `ingestion_fetchers()` and `ingestion_extractors()` hooks
- Expose `POST /api/ingest` REST endpoint

---

## Out of Scope

- Domain-specific extractor implementations (those belong in domain plugins)
- `yt-dlp` itself (lives in `integrations/ze-yt/`, registered as a `Fetcher` at
  container wiring time)
- Memory deduplication and consolidation (handled by `ze-memory`)
- Proactive ingestion scheduling (a `ProactiveJob` subclass, written separately in the
  plugin that needs it)

---

## Module Location

```
core/ze-ingestion/
└── ze_ingestion/
    ├── __init__.py           # public re-exports
    ├── types.py              # ContentType, IngestionRequest, RawContent,
    │                         # ProcessedContent, ExtractionResult, IngestionResult
    ├── errors.py             # FetchError, ProcessError, UnsupportedContentError
    ├── classifier.py         # ContentClassifier
    ├── fetchers/
    │   ├── __init__.py       # Fetcher protocol + FetcherRegistry
    │   ├── web.py            # WebFetcher (httpx)
    │   └── browser.py        # BrowserFetcher (ze-browser sidecar)
    ├── processors/
    │   ├── __init__.py       # Processor protocol + ProcessorRegistry
    │   ├── html.py           # HtmlProcessor
    │   ├── pdf.py            # PdfProcessor (pypdf)
    │   ├── audio.py          # AudioProcessor (OpenAI Whisper via OpenRouter)
    │   ├── image.py          # ImageProcessor (vision LLM via LLMClient)
    │   └── text.py           # TextProcessor (passthrough)
    ├── extractors/
    │   ├── __init__.py       # Extractor protocol + ExtractorRegistry
    │   └── llm.py            # LLMExtractor (default — summary, facts, entities, tags)
    ├── pipeline.py           # IngestionPipeline
    ├── store.py              # IngestionStore
    ├── sink.py               # MemorySink
    ├── agent.py              # IngestionAgent (@agent)
    └── migrations/
        └── zi001_ingested_content.py
```

```
integrations/ze-yt/
└── ze_yt/
    ├── __init__.py
    ├── client.py     # YtDlpClient (wraps yt-dlp subprocess)
    └── fetcher.py    # YtDlpFetcher — implements Fetcher protocol
```

---

## Data Structures

```python
# ze_ingestion/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ContentType(str, Enum):
    WEB_PAGE    = "web_page"
    VIDEO       = "video"       # YouTube, Instagram Reels, TikTok, Vimeo, …
    AUDIO       = "audio"       # podcast, voice memo, mp3
    PDF         = "pdf"
    IMAGE       = "image"
    PLAIN_TEXT  = "plain_text"
    DOCUMENT    = "document"    # Word, spreadsheet, etc.
    UNKNOWN     = "unknown"


@dataclass
class IngestionRequest:
    # Exactly one of url / file_bytes must be set.
    url: str | None = None
    file_bytes: bytes | None = None
    mime_type: str | None = None    # caller hint; classifier may override
    label: str | None = None        # optional user-supplied label / title


@dataclass
class RawContent:
    content_type: ContentType
    source_url: str | None
    data: bytes
    mime_type: str


@dataclass
class ProcessedContent:
    content_type: ContentType
    source_url: str | None
    text: str                       # always plain text after processing
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    summary: str
    facts: list[str]
    entities: list[str]
    tags: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    ingestion_id: str
    content_type: ContentType
    source_url: str | None
    summary: str
    facts_count: int
    entities_count: int
    tags: list[str]
```

---

## Protocol Definitions

```python
# ze_ingestion/fetchers/__init__.py

class Fetcher(Protocol):
    """Fetches raw bytes from a URL."""
    url_patterns: list[str]   # regex patterns; first matching Fetcher wins

    async def fetch(self, url: str) -> RawContent: ...


# ze_ingestion/processors/__init__.py

class Processor(Protocol):
    """Converts RawContent to plain text ProcessedContent."""
    content_types: list[ContentType]  # ContentTypes this processor handles

    async def process(self, raw: RawContent) -> ProcessedContent: ...


# ze_ingestion/extractors/__init__.py

class Extractor(Protocol):
    """Extracts structured knowledge from processed text."""
    content_types: list[ContentType]  # ContentTypes this extractor handles;
                                       # empty list = handles ALL types

    async def extract(self, content: ProcessedContent) -> ExtractionResult: ...
```

---

## Pipeline

```python
# ze_ingestion/pipeline.py

class IngestionPipeline:
    def __init__(
        self,
        classifier: ContentClassifier,
        fetchers: list[Fetcher],        # sorted by specificity; first match wins
        processors: list[Processor],
        extractors: list[Extractor],    # ALL matching extractors run; results merged
        store: IngestionStore,
        memory_sink: MemorySink,
    ) -> None: ...

    async def ingest(self, request: IngestionRequest) -> IngestionResult: ...
```

### Pipeline execution steps

The `IngestionPipeline.ingest()` method accepts an optional `reporter: ProgressReporter | None`
so the `IngestionAgent` can pass its context-bound reporter through. Each step emits a
progress key before it starts work; long steps (fetch, process, extract) emit one key
per stage so the user sees continuous feedback.

1. **Classify** — `ContentClassifier` determines `ContentType` from URL pattern, MIME
   hint, or magic bytes sniff on the first 512 bytes of file data.
   → emit `ingestion.classifying`
2. **Fetch** — if `request.url` is set, walk `fetchers` in order; first whose
   `url_patterns` matches the URL is used. Falls back to `WebFetcher`.
   If `request.file_bytes` is set, wrap bytes in `RawContent` directly (no fetch).
   → emit `ingestion.fetching` (URL inputs only)
3. **Process** — find the first `Processor` whose `content_types` includes the
   classified type; run it to get `ProcessedContent`.
   → emit `ingestion.processing.<content_type>` (e.g. `ingestion.processing.video`,
   `ingestion.processing.pdf`). Falls back to `ingestion.processing.default` if the
   key is not defined for that content type.
4. **Extract** — collect all `Extractor`s whose `content_types` includes the type
   (or is empty / ALL). Run them in parallel (`asyncio.gather`). Merge results:
   - `summary`: join non-empty summaries with `"\n\n"` (first extractor's summary
     is the primary; appended summaries are supplementary)
   - `facts`, `entities`, `tags`: union, deduplication by exact string match
   - `metadata`: dict merge (later extractors overwrite on key conflict)
   → emit `ingestion.extracting`
5. **Store** — write `ProcessedContent` + merged `ExtractionResult` to
   `ingested_content` table via `IngestionStore`.
6. **Sink** — push each fact string to `MemorySink` (which calls `ze-memory`'s
   fact ingestion API, tagging facts with `source=ingestion:<ingestion_id>`).
   → emit `ingestion.saving`

---

## Extractor merge invariant

All extractors run regardless of partial failure. If one extractor raises, its
`ExtractionResult` is skipped and the error is logged; the pipeline continues with
the remaining extractors' results. At least one extractor (the default `LLMExtractor`)
is always registered, so the merge never produces an empty result.

---

## `ZePlugin` hooks

```python
# ze_plugin/plugin.py — new optional overrides

def ingestion_fetchers(self) -> list[Fetcher]:
    """Return Fetcher instances this plugin contributes to the ingestion pipeline."""
    return []

def ingestion_extractors(self) -> list[Extractor]:
    """Return Extractor instances this plugin contributes to the ingestion pipeline."""
    return []
```

The container collects these at startup — same pattern as `data_domains()` and
`signal_sources()`.

---

## Database Schema

```sql
-- ze_ingestion/migrations/zi001_ingested_content.py

CREATE TABLE ingested_content (
    id              TEXT        PRIMARY KEY,
    source_url      TEXT,
    content_type    TEXT        NOT NULL,
    raw_text        TEXT        NOT NULL,
    summary         TEXT,
    facts           JSONB       NOT NULL DEFAULT '[]',
    entities        JSONB       NOT NULL DEFAULT '[]',
    tags            JSONB       NOT NULL DEFAULT '[]',
    metadata        JSONB       NOT NULL DEFAULT '{}',
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ingested_content_type_idx ON ingested_content (content_type);
CREATE INDEX ingested_content_at_idx   ON ingested_content (ingested_at DESC);
```

Migration branch prefix: `zi`. First revision: `zi001`.

`ze-api/migrate.py` gains a `_ZE_INGESTION_VERSIONS` constant pointing to
`ze_ingestion.migrations`.

---

## `IngestionAgent`

```python
# ze_ingestion/agent.py

_AGENT_INSTRUCTIONS = """
You are Ze's ingestion assistant. When the user sends you a URL, file, or block of
text they want Ze to learn from, extract it and run the ingestion pipeline.

Use the `ingest_url` tool for URLs and `ingest_text` for raw text or file content
already extracted. Always confirm to the user what was ingested: content type,
number of facts extracted, and the summary.
"""

@agent
class IngestionAgent(BaseAgent):
    description = "Ingest external content — URLs, PDFs, videos, audio — into Ze's memory"
    model = "..."
    intents = [
        "save this link",
        "learn from this URL",
        "ingest this PDF",
        "save this article",
        "watch this video and remember it",
        "read this and learn",
    ]
    tools = ["ingest_url", "ingest_text"]
    timeout = 120
```

### Tools

```python
@tool
async def ingest_url(url: str) -> dict: ...
    """Fetch, process, and ingest content at the given URL into Ze's memory."""

@tool
async def ingest_text(text: str, label: str | None = None) -> dict: ...
    """Ingest raw text or pre-extracted document content into Ze's memory."""
```

The agent calls `await self.emit(ctx, "ingestion.starting")` before handing off to the
pipeline. The pipeline then drives subsequent emissions via its injected `reporter`.
This means progress continues even during long-running steps (video transcription,
LLM extraction) that occur inside tool execution.

---

## Progress Messages

Progress keys live in `ze_ingestion/locales/en.yaml` (same structure as other plugins).
The `IngestionAgent` locale is loaded and merged into `ProgressTranslations` at startup.

```yaml
# core/ze-ingestion/ze_ingestion/locales/en.yaml

ingestion:
  starting:
    - "On it, let me pull that in..."
    - "Got it, ingesting now..."
  classifying:
    - "Figuring out what this is..."
  fetching:
    - "Fetching the content..."
    - "Grabbing it now..."
  processing:
    default:
      - "Processing the content..."
    video:
      - "Transcribing the video — this may take a moment..."
      - "Extracting audio and transcribing..."
    audio:
      - "Transcribing the audio..."
    pdf:
      - "Reading the PDF..."
    image:
      - "Reading the image..."
    web_page:
      - "Reading the page..."
  extracting:
    - "Extracting what's useful..."
    - "Pulling out the key information..."
  saving:
    - "Saving to memory..."
```

### Emit sequence for a typical video URL

```
ingestion.starting          ← IngestionAgent, before tool call
ingestion.classifying       ← pipeline step 1
ingestion.fetching          ← pipeline step 2
ingestion.processing.video  ← pipeline step 3 (longest — yt-dlp + Whisper)
ingestion.extracting        ← pipeline step 4
ingestion.saving            ← pipeline step 6
```

### `ProgressReporter` wiring in the pipeline

```python
# ze_ingestion/pipeline.py

async def ingest(
    self,
    request: IngestionRequest,
    reporter: ProgressReporter | None = None,
) -> IngestionResult:
    async def emit(key: str) -> None:
        if reporter:
            await reporter.emit(key)
    ...
```

Tools receive the reporter via the agent context the same way other agents do —
`BaseAgent.agentic_loop` passes the bound `ProgressReporter` into the tool execution
context. The `ingest_url` and `ingest_text` tools extract it and forward it to
`IngestionPipeline.ingest()`.

---

## `integrations/ze-yt/` — YtDlp integration

```
integrations/ze-yt/
└── ze_yt/
    ├── __init__.py
    ├── client.py     # YtDlpClient — thin subprocess wrapper around yt-dlp
    └── fetcher.py    # YtDlpFetcher(Fetcher) — url_patterns covers YouTube,
                      #   Instagram, TikTok, Vimeo, Twitter/X video URLs
```

`YtDlpFetcher.fetch(url)`:
1. Runs `yt-dlp --extract-audio --audio-format mp3 -o <tmpfile> <url>` via asyncio subprocess
2. Returns `RawContent(content_type=ContentType.AUDIO, data=<mp3 bytes>, ...)`
3. The `AudioProcessor` in `ze-ingestion` picks it up and transcribes via OpenRouter Whisper

`ze-api/container.py` instantiates `YtDlpFetcher` and passes it into `IngestionPipeline`
alongside plugin-contributed fetchers. `ze-yt` is an optional dep — if not installed or
not configured, no `YtDlpFetcher` is registered and video URLs fall back to `WebFetcher`.

---

## `POST /api/ingest` route

```
POST /api/ingest
Content-Type: multipart/form-data
  url:   (optional) URL to ingest
  file:  (optional) uploaded file
  label: (optional) user-supplied title

Response 200:
{
  "ingestion_id": "...",
  "content_type": "pdf",
  "summary": "...",
  "facts_count": 12,
  "tags": ["finance", "investment"]
}
```

Exactly one of `url` or `file` must be present; 422 otherwise.

---

## `ContentClassifier`

Classification priority order:
1. **URL pattern matching** — well-known domains (youtube.com, youtu.be → VIDEO;
   instagram.com/reel → VIDEO; *.pdf URL → PDF; etc.)
2. **MIME type hint** — if caller provides `mime_type`
3. **Magic bytes sniff** — first 512 bytes of fetched/uploaded data
   (`%PDF-` → PDF, `ID3` / `ftyp` → AUDIO/VIDEO, etc.)
4. **Fallback** — `ContentType.UNKNOWN`; `TextProcessor` handles it as plain text

---

## Dependency graph after this phase

```
ze-data         (no ze deps)                              core/
ze-agents       (no ze deps)                              core/
ze-ingestion  → ze-agents, ze-data, ze-browser, ze-memory core/
ze-plugin     → ze-agents, ze-data                        core/
ze-sdk        → ze-agents, ze-plugin, ze-proactive,
                ze-memory, ze-ingestion                   core/
ze-yt           (no ze deps — wraps yt-dlp subprocess)    integrations/
ze-api        → ze-core, ze-sdk, ..., ze-ingestion, ze-yt apps/
```

---

## Implementation Notes

- `AudioProcessor` calls OpenRouter's Whisper endpoint via `LLMClient`. The client
  is injected — `ze-ingestion` never imports `ze-core` directly.
- `ImageProcessor` uses a vision-capable model (e.g. `google/gemini-flash-1.5`) via
  `LLMClient` with image bytes encoded as base64.
- `BrowserFetcher` delegates to `ze-browser`'s `BrowserClient` — used for JS-heavy
  pages where `WebFetcher` (httpx) returns an empty or skeleton DOM.
- `yt-dlp` must be installed as a system dependency or via `uv` tool. The
  `YtDlpClient` runs it as a subprocess with a temp directory; cleanup is always done
  in a `finally` block.
- `IngestionStore` is the archive of raw processed text. `MemorySink` is lossy —
  only the extracted facts flow into memory, not the full text. The archive is the
  authoritative record.
- The `ingest_url` and `ingest_text` tools are registered in `ze-ingestion`'s agent
  module, not in `ze-personal`. `IngestionAgent` routes independently.

---

## Open Questions

- [x] Run all extractors or just the most specific? **Decision: run all matching
  extractors in parallel and merge results.**
- [x] Where does yt-dlp live? **Decision: `integrations/ze-yt/` as a thin subprocess
  wrapper; optional dep wired by `ze-api` container.**
- [x] Should `IngestionAgent` stream progress messages while the pipeline runs?
  **Decision: yes.** Each pipeline stage emits a progress key. Reporter is passed
  from agent → tool → pipeline via the existing `ProgressReporter` injection pattern.
  Locale file lives in `ze_ingestion/locales/en.yaml`.
- [ ] `GET /api/ingest` listing endpoint — search/filter archived ingestions?
  Deferred unless needed for UI.
- [ ] What happens when the same URL is ingested twice? Dedup by `source_url` +
  timestamp, or allow duplicates? Current spec: allow duplicates, dedup is `ze-memory`'s
  concern at the fact level.
