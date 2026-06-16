# News Package — Spec

> **Package:** `ze-news` (new standalone package, peer to `ze-personal`)
> **Phase:** 37
> **Status:** Done
> **Depends on:** Phase 20 ([28-goal-engine.md](28-goal-engine.md) package reorg), ZePlugin ABC ([arch/plugin-agents.md](../arch/plugin-agents.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze-news` package scaffold | ✅ Done |
| `NewsSource` ABC + registry | ✅ Done |
| `RSSSource` implementation | ✅ Done |
| `NewsStore` (Postgres + embeddings) | ✅ Done |
| `NewsAgent` + tools | ✅ Done |
| `NewsPlugin(ZePlugin)` | ✅ Done |
| `NewsFetchJob` (proactive refresh + `force=True` for on-demand) | ✅ Done |
| `refresh_news` tool (on-demand fetch bypassing interval guard) | ✅ Done |
| DB migration | ✅ Done |
| Config schema | ✅ Done |
| `MorningBriefing` news wiring (`ze/jobs/briefing.py`) | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze currently has no awareness of the world beyond what the user tells it or what a
one-shot web search returns. A persistent news layer lets Ze answer "what's happening
in X?" queries from a local store, inject relevant headlines into the morning briefing,
and surface news proactively when events are likely to matter to the user.

The news system is built as a standalone `ze-news` package that registers via
`ZePlugin`. This keeps news concerns out of `ze-personal` and `ze-core`, and
demonstrates the plugin model as a genuine extension seam — new information-gathering
domains (e.g., academic papers, market data) can follow the same pattern without
touching the core monorepo.

Global vs. local distinction is a config concern, not a code branch. Sources are tagged
in `config.yaml`; the `NewsSource` ABC is identical for both.

---

## Responsibilities

- Define the `NewsSource` ABC — the single extension point for adding new source types.
- Maintain a `SourceRegistry` populated at startup from `config.yaml`.
- Periodically fetch and store articles from all registered sources via `NewsFetchJob`.
- Deduplicate articles by URL; prune articles older than the configured retention window.
- Embed article titles + summaries with `paraphrase-multilingual-MiniLM-L12-v2` for semantic retrieval.
- Expose a `NewsStore` for semantic and keyword search, consumed by `NewsAgent`.
- Answer natural-language news queries via `NewsAgent`.
- Expose a `NewsPlugin(ZePlugin)` that wires all of the above into the Ze container.

---

## Out of Scope

- **Real-time streaming** — articles are fetched on a schedule, not streamed on demand.
- **Full article content storage** — only title, summary/description, URL, source key,
  published date, and tags are stored. Full text is not fetched or embedded.
- **User-specific personalisation** — source selection is global config, not per-user.
  (Single-user system; if this changes, revisit.)
- **Paid news APIs** (NewsAPI, GNews) in the initial implementation — RSS covers the
  launch use case with zero extra credentials. API-backed sources can be added later by
  implementing `NewsSource`.
- **Deduplication across sources** — URL is the dedup key. Two sources covering the
  same story with different URLs produce two records. Semantic dedup is a future concern.
- **Morning briefing integration in this phase** — the briefing job in `ze/jobs/` can
  call `NewsStore.get_recent()` directly once this package lands. Wiring that is a
  follow-on change to `ze/`, not to `ze-news`.

---

## Package Location

```
packages/
  ze-news/
    pyproject.toml
    ze_news/
      __init__.py
      plugin.py          # NewsPlugin(ZePlugin)
      types.py           # Article, SourceConfig, SourceTag
      registry.py        # SourceRegistry
      store.py           # NewsStore (Postgres + embeddings)
      sources/
        __init__.py
        base.py          # NewsSource ABC
        rss.py           # RSSSource
      agents/
        agent.py         # @agent NewsAgent
        tools.py         # @tool search_news, get_headlines
      jobs/
        fetch.py         # NewsFetchJob (ProactiveJob)
    tests/
      test_registry.py
      test_store.py
      test_rss_source.py
      agents/
        test_news_agent.py
      jobs/
        test_fetch_job.py
  ze/
    migrations/          # new migration: 0NNN_news_articles.sql
    ze/
      jobs/
        briefing.py      # add get_recent() call to MorningBriefing (in-scope change)
```

### Package dependency graph (updated)

```
ze-browser  (no ze deps)
ze-core     (no ze deps)
ze-personal → ze-core
ze-news     → ze-core          ← new
ze          → ze-core, ze-personal, ze-browser, ze-news
```

`ze-news` depends only on `ze-core` for `ZePlugin`, `BaseAgent`, `@agent`, `@tool`,
`OpenRouterClient`, `ProactiveJob`, and the shared embeddings singleton. It has no
dependency on `ze-personal`.

---

## Source Abstraction

### `NewsSource` ABC

```python
# ze_news/sources/base.py

from abc import ABC, abstractmethod
from ze_news.types import Article

class NewsSource(ABC):
    key: str        # unique identifier, matches config key

    @abstractmethod
    async def fetch(self, limit: int = 20) -> list[Article]:
        """Fetch up to `limit` recent articles. Never raises — returns [] on error."""
```

Every source is stateless — it reads from an external endpoint and returns `Article`
objects. No DB interaction inside sources. Error handling is the source's responsibility;
a fetch failure returns `[]` and logs a warning.

### `RSSSource`

```python
# ze_news/sources/rss.py

class RSSSource(NewsSource):
    def __init__(self, key: str, url: str, tags: list[str]) -> None: ...
    async def fetch(self, limit: int = 20) -> list[Article]: ...
```

Uses `httpx` (already a transitive dependency via `ze-core`) to fetch the feed and
`feedparser` to parse Atom/RSS. Strips HTML from summaries. Published date falls back
to `now()` if absent.

### `SourceRegistry`

```python
# ze_news/registry.py

class SourceRegistry:
    def __init__(self, sources: list[NewsSource]) -> None: ...

    def all(self) -> list[NewsSource]: ...
    def by_tag(self, tag: str) -> list[NewsSource]: ...
    def by_key(self, key: str) -> NewsSource | None: ...
```

Built from config at container startup. Adding a new source type requires only a new
`NewsSource` subclass and a config entry — no changes to the registry.

---

## Data Structures

```python
# ze_news/types.py

from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Article:
    url: str                       # primary key / dedup key
    source_key: str                # registry key of the source that produced it
    title: str
    summary: str                   # first 500 chars of description/content
    published_at: datetime
    tags: list[str] = field(default_factory=list)   # e.g. ["global", "tech"]

@dataclass
class SourceConfig:
    key: str
    type: str                      # "rss" | future types
    url: str
    tags: list[str]
```

---

## Database Schema

```sql
-- migrations/0NNN_news_articles.sql

CREATE TABLE news_articles (
    url             TEXT PRIMARY KEY,
    source_key      TEXT NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT NOT NULL DEFAULT '',
    published_at    TIMESTAMPTZ NOT NULL,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    embedding       VECTOR(384),
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_news_articles_published_at ON news_articles (published_at DESC);
CREATE INDEX idx_news_articles_source_key   ON news_articles (source_key);
CREATE INDEX idx_news_articles_tags         ON news_articles USING GIN (tags);
```

`VECTOR(384)` requires `pgvector`. The `embedding` column is nullable — articles without
embeddings are still queryable by keyword and date, just not by semantic similarity.

---

## Storage Layer

### `NewsStore`

```python
# ze_news/store.py

class NewsStore:
    def __init__(self, pool: asyncpg.Pool, embedder: Embedder) -> None: ...

    async def upsert(self, articles: list[Article]) -> int:
        """Insert or ignore on URL conflict. Returns count of new rows."""

    async def search(self, query: str, limit: int = 10, tags: list[str] | None = None) -> list[Article]:
        """Semantic search. Falls back to recency sort if no embedding available."""

    async def get_recent(self, limit: int = 20, tags: list[str] | None = None) -> list[Article]:
        """Fetch most recent articles, optionally filtered by tag."""

    async def prune(self, older_than_days: int) -> int:
        """Delete articles older than `older_than_days`. Returns count deleted."""
```

Embeddings are computed over `f"{article.title}. {article.summary}"` using the shared
`paraphrase-multilingual-MiniLM-L12-v2` singleton from `ze_core.embeddings`. Embedding is computed in
`upsert` before the DB write. Semantic search uses cosine similarity via `pgvector`'s
`<=>` operator, same pattern as `EmbeddingRouter`.

---

## Proactive Fetch Job

```python
# ze_news/jobs/fetch.py

class NewsFetchJob(ProactiveJob):
    id = "news_fetch"
    schedule = "*/30 * * * *"    # every 30 minutes; overridable from config

    def __init__(self, registry: SourceRegistry, store: NewsStore) -> None: ...

    async def run(self) -> None:
        for source in self._registry.all():
            articles = await source.fetch(limit=50)
            new_count = await self._store.upsert(articles)
            log.info("news_fetch_done", source=source.key, new=new_count)
        pruned = await self._store.prune(older_than_days=self._retention_days)
        if pruned:
            log.info("news_prune_done", pruned=pruned)
```

Runs every 30 minutes by default. Schedule and retention window are configurable in
`config.yaml`. Each source fetch is independent — a failure in one source does not abort
the others.

---

## News Agent

```python
# ze_news/agents/agent.py

@agent
class NewsAgent(BaseAgent):
    description = "Searches and summarises news from configured sources"
    model = "..."                  # from config; e.g. openai/gpt-4o-mini
    capabilities = ["news"]
    intent_map = {
        "news query": ["what's in the news", "latest headlines", "what's happening with"],
    }
    tools = [search_news, get_headlines]
    timeout = 60
```

```python
# ze_news/agents/tools.py

@tool
async def search_news(query: str, limit: int = 10) -> list[dict]: ...

@tool
async def get_headlines(tags: list[str] | None = None, limit: int = 20) -> list[dict]: ...
```

`search_news` delegates to `NewsStore.search()`. `get_headlines` delegates to
`NewsStore.get_recent()`. Both tools receive the store via `config["configurable"]`
(injected by `NewsPlugin.configurable_services()`).

---

## Plugin

```python
# ze_news/plugin.py

class NewsPlugin(ZePlugin):
    def __init__(self, registry: SourceRegistry, store: NewsStore, fetch_job: NewsFetchJob) -> None:
        self._registry = registry
        self._store = store
        self._fetch_job = fetch_job

    def agents(self) -> list[type[BaseAgent]]:
        from ze_news.agents.agent import NewsAgent
        return [NewsAgent]

    def jobs(self) -> list[ProactiveJob]:
        return [self._fetch_job]

    def configurable_services(self) -> dict[str, Any]:
        return {"news_store": self._store}

    def agent_module_paths(self) -> list[str]:
        return ["ze_news.agents.agent"]
```

The `ze/container.py` constructs `NewsPlugin` from the config-driven source list and
registers it alongside `PersonalPlugin`.

---

## Configuration

```yaml
# config/config.yaml

news:
  fetch_schedule: "*/30 * * * *"   # cron; default every 30 min
  retention_days: 7
  sources:
    - key: bbc_world
      type: rss
      url: "https://feeds.bbci.co.uk/news/world/rss.xml"
      tags: [global, general]
    - key: bbc_tech
      type: rss
      url: "https://feeds.bbci.co.uk/news/technology/rss.xml"
      tags: [global, tech]
    - key: hn
      type: rss
      url: "https://hnrss.org/frontpage"
      tags: [global, tech, hacker-news]
    - key: local_pt
      type: rss
      url: "https://www.publico.pt/rss"
      tags: [local, pt]
```

Tags are free-form strings. The `global` / `local` distinction is purely a tag
convention — no special handling in code. `get_headlines(tags=["local"])` returns
articles from local sources; `get_headlines(tags=["global"])` returns global ones.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.plugin.ZePlugin` | Plugin ABC |
| `ze_core.orchestration.base_agent.BaseAgent` | Agent base class |
| `ze_core.orchestration.registry.agent` | `@agent` decorator |
| `ze_core.orchestration.tool.tool` | `@tool` decorator |
| `ze_core.proactive.job.ProactiveJob` | Scheduled fetch job |
| `ze_core.embeddings` | Shared `paraphrase-multilingual-MiniLM-L12-v2` singleton |
| `ze_core.openrouter` | LLM calls in `NewsAgent` |
| `httpx` | RSS feed fetching (already a dep via ze-core) |
| `feedparser` | RSS/Atom parsing — new dep for `ze-news` only |
| `pgvector` | `VECTOR` column type in Postgres — already used by ze |

---

## Implementation Notes

- **Why Postgres-backed and not fetch-on-demand?** Fetch-on-demand means every news
  query hits external RSS endpoints synchronously. Postgres-backed means queries are
  local and fast, semantic search is possible, and the agent can answer "what did I miss
  while I was offline?" The fetch job's 30-minute cadence is an acceptable staleness
  tradeoff.
- **Why not store full article content?** Full text multiplies storage cost, requires
  HTML parsing, and is rarely needed — the user typically wants a summary or a link.
  If full-text retrieval becomes a use case, add a `content` column and a secondary
  fetch step in `RSSSource`.
- **`feedparser` as the only new dep.** The RSS parsing problem is fully solved by
  `feedparser`. There is no reason to implement XML parsing or Atom/RSS dialect handling
  from scratch. `feedparser` disables XML entity expansion by default, which addresses
  the primary XXE risk from untrusted RSS content.
- **`feedparser.parse()` must run in a thread pool.** Pattern: fetch raw bytes with
  `httpx.AsyncClient`, then `await asyncio.wait_for(loop.run_in_executor(None, feedparser.parse, text), timeout=10.0)`.
  This is a correctness requirement — a blocking parse on the event loop thread during
  a multi-source fetch run stalls Telegram webhook handling.
- **Tags as `TEXT[]`.** GIN-indexed array in Postgres is simpler than a join table and
  sufficient for the filtering patterns needed (`tags && ARRAY['local']`).
- **`ze-news` depends only on `ze-core`.** This keeps the package graph clean. If
  news-specific behaviour needs access to contacts or goals (e.g., "news relevant to my
  current goal"), inject the relevant stores via `configurable_services` from `ze/`,
  not by adding `ze-personal` as a dependency.

---

## Open Questions

- [x] **Which model for `NewsAgent`?** → Use `openai/gpt-4o-mini` as default, same as
  other lightweight agents. Configurable via `news.model` in `config.yaml`. News queries
  are summarisation tasks — a reasoning-grade model is unnecessary.
- [x] **Should `NewsFetchJob` embed articles in the background or inline in `upsert`?**
  → Inline. `paraphrase-multilingual-MiniLM-L12-v2` is CPU-local; embedding 50 articles takes ~1 s total
  — acceptable in a background job that runs every 30 minutes. No background queue needed.
- [x] **Morning briefing integration.** → Scoped into Phase 37 implementation window,
  not deferred. Add `NewsStore.get_recent(tags=["global"], limit=5)` call to
  `MorningBriefing` in `ze/jobs/briefing.py`. Without this, the package has no
  proactive value. Delta is ~20 lines.
- [x] **`feedparser` is sync.** → Resolved: fetch raw bytes with `httpx.AsyncClient`,
  then parse inside `run_in_executor(None, feedparser.parse, text)`. Add
  `asyncio.wait_for(..., timeout=10.0)` around the executor call to bound per-source
  fetch time. This keeps the event loop clean regardless of feed size or parse time.
- [x] **Source health monitoring.** → Deferred. Log failures per source with `source_key`
  and error type. Monitor `upsert` new-row count per source per run to detect silent
  degradation (T4). Telegram alerting after N consecutive failures is a follow-on.

## Routing Intent Guidance

`NewsAgent` owns **digest-style and corpus queries**: "what's in the news today?",
"any tech headlines this week?", "what happened in Portugal?". These are answered from
the local article store.

The **research agent** (with `openrouter:web_search`) owns **breaking news and specific
fact lookups**: "what just happened in X?", "is Y confirmed?". Web search is strictly
more up-to-date than the 30-minute fetch cadence.

The `intent_map` in `NewsAgent` must reflect this distinction clearly to avoid routing
ambiguity. If post-deployment evals show miss rate > 20% on digest queries, enrich the
intent map with more natural-language variants (see pre-mortem T2).
