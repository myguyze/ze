# Pre-Mortem: Phase 37 — News Package

**Date**: 2026-06-07
**Status**: Draft
**Spec**: [37-news-package.md](../037-news-package/spec.md)

---

## Risk Summary

- **Tigers**: 5 (1 launch-blocking, 2 fast-follow, 2 track)
- **Paper Tigers**: 4
- **Elephants**: 3

---

## Launch-Blocking Tigers

| # | Risk | Likelihood | Impact | Mitigation | Owner | Deadline |
|---|------|------------|--------|------------|-------|----------|
| T1 | `feedparser.parse()` is a blocking call — runs on the event loop thread, stalling the asyncpg connection pool and potentially delaying Telegram responses during fetch runs | High | High | Fetch raw feed bytes with `httpx.AsyncClient`; pass text to `feedparser.parse()` inside `asyncio.get_event_loop().run_in_executor(None, feedparser.parse, text)`. Resolved in spec before implementation begins. | — | Before implementation |

**Why launch-blocking**: Ze's event loop handles Telegram webhook callbacks and graph invocations concurrently. A blocking call during a fetch run (which processes N sources) can stall all in-flight requests for seconds. This is a correctness issue, not a performance nit.

---

## Fast-Follow Tigers

| # | Risk | Likelihood | Impact | Planned Response | Owner |
|---|------|------------|--------|-----------------|-------|
| T2 | `NewsAgent` routing miss — user says "what's in the news?" but `EmbeddingRouter` scores the research agent higher, sending the query to web search instead | Medium | Medium | After first deployment, run routing evals against 10 representative news intents. If miss rate > 20%, enrich `intent_map` with more natural-language variants and re-embed. | — |
| T3 | Morning briefing integration is deferred but is the primary proactive value of the package. Without it, news is only accessible via explicit query — a low-value interaction users can satisfy with a browser tab | High | Medium | Wire `NewsStore.get_recent(tags=["global"], limit=5)` into `MorningBriefing` in the same implementation window as Phase 37 (not a separate phase). Treat as required fast-follow, not optional. | — |

---

## Track Tigers

| # | Risk | Trigger Condition | Monitor Via |
|---|------|-------------------|-------------|
| T4 | URL-based dedup is fragile — same article appears with different URLs due to tracking parameters, CDN redirects, or source feed updates. Store fills with near-duplicates over time. | Noticeable duplicate headlines in `get_headlines()` output, or `news_articles` row count growing faster than `(sources × articles_per_source × retention_days)` would predict | Log `upsert` new-row count per source per run. If a source consistently produces > 2× expected new rows, investigate. |
| T5 | `feedparser` parses untrusted external XML. A malicious or malformed feed could trigger XML entity expansion (XXE) or pathological parse time. | A feed consistently causes fetch timeouts or log errors | `feedparser` disables entity expansion by default. Monitor `run_in_executor` timeout; add a 10s per-source timeout to the executor call. |

---

## Paper Tigers

**PT1 — pgvector not available**
Already enabled via `CREATE EXTENSION IF NOT EXISTS vector` in migration 001. Zero setup risk; the migration is idempotent.

**PT2 — Storage growth**
7-day retention × 50 articles × 10 sources = ~3,500 rows max. With a 500-char summary and a 384-float embedding (~1.5 KB/row), peak storage is ~5 MB. Trivial. `prune()` runs every fetch cycle.

**PT3 — RSS feed reliability**
Feeds go down, move, or return 404. Already handled by design: `fetch()` returns `[]` on any error and logs a warning. A failing source silently produces zero articles — no crash, no user-visible error.

**PT4 — Embedding latency at upsert time**
`paraphrase-multilingual-MiniLM-L12-v2` is already loaded as a singleton at startup. Embedding 50 articles inline takes ~15–25 ms each on CPU, so ~1 s total per source. In a background job that runs every 30 minutes, this is acceptable. No background embedding queue needed.

---

## Elephants in the Room

**E1 — Is Phase 37 useful without the briefing?**
The spec defers briefing integration to a follow-on. But an explicit news query ("what's in the news?") is low-value — the user can open a browser. Ze's differentiation is *proactive* news awareness. If Phase 37 ships without briefing wiring, it may feel like infrastructure with no user-facing payoff.

> Suggested conversation: "Should we scope briefing integration into Phase 37 rather than deferring it? The delta is ~20 lines in `MorningBriefing`."

**E2 — Source curation is the real ongoing work, not the code**
The code ships once. But RSS feeds die, move to paywalled domains, change format, or degrade in quality. The spec has no answer for long-term source health beyond "log and watch." The team (in this case: one person) implicitly takes on feed maintenance as an operational burden.

> Suggested conversation: "What's the bar for adding or removing sources? Should there be a `/news sources` command to check source health from Telegram?"

**E3 — NewsAgent competes with Ze's existing web search**
`openrouter:web_search` (available to the research agent) is strictly more up-to-date than a 30-minute-stale local cache. For breaking news, the research agent wins. The news package's genuine advantages — offline-capable, semantic search over a curated corpus, briefing integration — are not clearly articulated to the user. Without that framing, the routing question (T2) becomes harder: *why* should a news query go to `NewsAgent` instead of the research agent?

> Suggested conversation: "Should the spec explicitly define when `NewsAgent` wins over web search? E.g. 'weekly digest / briefing' goes to news store; 'breaking news / specific fact' goes to web search."

---

## Go/No-Go Checklist

- [ ] T1 resolved: `feedparser.parse()` wrapped in `run_in_executor` — spec updated before implementation starts
- [ ] T3 scoped: morning briefing integration included in Phase 37 implementation window
- [ ] Routing evals planned for post-deployment (T2)
- [ ] Per-source `upsert` count logging in place for T4 monitoring
- [ ] Executor timeout (10 s per source) added to `RSSSource.fetch()` for T5
- [ ] E3 articulated in spec: explicit guidance on `NewsAgent` vs web search routing intent

---

## Recommended Actions Before Implementation

1. **Update spec**: mark `feedparser` executor pattern as the resolved implementation approach (closes OQ4).
2. **Scope briefing integration into Phase 37**: add `MorningBriefing` wiring to the implementation status table and module location (closes OQ3).
3. **Add routing intent guidance**: clarify in the spec that `NewsAgent` owns digest/briefing-style queries; the research agent owns breaking news and specific fact lookups (closes E3).
4. **Add executor timeout**: spec `RSSSource.fetch()` with a 10 s `asyncio.wait_for` wrapping the executor call.
