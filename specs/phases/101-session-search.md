# Phase 101 — Session Search & Titles

> **Status:** Pending
> **Depends on:** Phase 90 — History side panel (`ChatSidePanel` / `SessionList`); Phase 45 — `messages` table + WebSocket turns; Phase 52 — session-grouped episode consolidation (`memory_session_summaries`)
> **Enables:** Jump-to-message in chat (future), nav sidebar search, smarter session list at scale
> **Packages touched:** `core/ze-core`, `core/ze-memory`, `apps/ze-api`, `apps/ze-web`

---

## Summary

Chat history is currently a flat, recency-sorted list with no search. Session titles are
the first 60 characters of the user's opening message, frozen forever — often useless
("hey", "can you help me with…"). This phase adds Postgres full-text search across
conversation content and replaces placeholder titles with LLM-generated labels after the
first exchange. The History tab in the chat side panel gets a search field; results show
match snippets and which layer matched (live message, session summary, or metadata).

---

## Goals

- `GET /api/v0/sessions/search?q=…` returns ranked sessions with highlighted snippets.
- Search covers live `messages.text`, `sessions.title` / `preview`, and `memory_session_summaries.summary`.
- After the first completed assistant reply, generate a short session title asynchronously (≤8 words) and persist with `update_title=True`.
- Existing sessions keep working; title generation is best-effort and never blocks the reply path.
- History panel: debounced search input; empty query falls back to cursor-paginated `listSessions`.
- `SessionRow` displays search snippets and a subtle match-source label when searching.
- `GET /api/v0/sessions` returns cursor-paginated results (`before` + `next_before`), matching the memory feed pattern.
- History panel infinite scroll loads older sessions when the user reaches the list bottom (browse mode only).

## Non-Goals

- Semantic / embedding search (FTS first; revisit if recall is insufficient).
- Searching trace JSON, tool payloads, or `messages.components`.
- Jump-to matched message inside the chat transcript (follow-up phase).
- Re-titling when conversation topic drifts (v1: one-shot after first exchange).
- Nav sidebar (`ChatNavGroup`) search UI (same API, deferred).
- Backfill job for titles on all historical sessions (optional manual script, not in DoD).
- Repo-wide pagination audit (goals, routing log, facts, etc.) — each endpoint paginated only when its UI needs it.
- Search-result pagination (`searchSessions` load-more) — fixed `limit` cap is sufficient in v1.

---

## Background

### Current session metadata

| Field | Written when | Update rule |
|-------|--------------|-------------|
| `sessions.title` | Every user message (`turns.py`) | `COALESCE` — first write wins |
| `sessions.preview` | Every assistant reply | Always overwritten (last 120 chars) |

```python
# apps/ze-api/ze_api/api/websocket/turns.py (today)
title = text[:60].strip()          # first user message, frozen
preview = outcome.response[:120]   # latest assistant snippet
```

The UI (`SessionRow`) shows title + markdown preview. Titles are misleading; previews are
not searchable.

### Where conversation text actually lives

| Table | Key column | Content |
|-------|------------|---------|
| `messages` | `thread_id` | Full user + assistant turns (primary search target) |
| `sessions` | `id` (= `thread_id`) | Title + preview metadata |
| `memory_session_summaries` | `session_id` | Consolidated narrative after session episodes are archived (Phase 52) |
| `memory_episodes` | `session_id` | Per-turn prompt/response before consolidation |

`memory_episodes.session_id` and `messages.thread_id` share the same identifier namespace
as `sessions.id`. Episodes are **excluded from v1 FTS** to avoid duplicate hits against
live messages; session summaries cover archived conversation text.

### Prior art in-repo

Contacts search (`ze_personal/contacts/store.py`) uses `to_tsvector('english', …) @@ plainto_tsquery('english', $1)` with a GIN index. Same pattern here, but with `'simple'` config for multilingual user content (aligned with E5 multilingual embeddings).

---

## Design

### 1. Title generation

Fire-and-forget after the first successful assistant reply in a session (same hook that
updates `preview` in `turns.py` / `confirmation.py`).

```
User message ──► upsert(title=first 60 chars, title_source='user')
Assistant reply ──► upsert(preview=…)
                 └─► if title_source == 'user': asyncio.create_task(generate_title(...))
generate_title ──► LLM (haiku) ──► upsert(title=…, update_title=True, title_source='generated')
```

**Prompt contract:** single line, ≤8 words, no quotes, describes the user's intent. Input:
first user message + first assistant reply (truncated to 500 chars each).

**Fallback display chain** (frontend, unchanged API shape):

1. `title` when `title_source = 'generated'`
2. `title` when `title_source = 'user'` (legacy / pending generation)
3. `"Untitled chat"`

Do not overwrite a `generated` title on later turns.

### 2. Full-text search

#### Index strategy

Migration `zc023` (ze-core):

```sql
-- messages: primary index
CREATE INDEX IF NOT EXISTS messages_text_fts_idx
    ON messages USING gin(to_tsvector('simple', coalesce(text, '')));

-- sessions: title + preview metadata
CREATE INDEX IF NOT EXISTS sessions_metadata_fts_idx
    ON sessions USING gin(
        to_tsvector('simple',
            coalesce(title, '') || ' ' || coalesce(preview, '')
        )
    );

-- title provenance
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title_source TEXT
    CHECK (title_source IN ('user', 'generated'));
```

Migration `zm014` (ze-memory):

```sql
CREATE INDEX IF NOT EXISTS memory_session_summaries_fts_idx
    ON memory_session_summaries USING gin(
        to_tsvector('simple', coalesce(summary, ''))
    );
```

Use `'simple'` (not `'english'`) because Ze users write in multiple languages.

#### Search query

New method `SessionStore.search(query, *, limit=20) -> list[SessionSearchHit]`.

Three-way union, deduplicated by `session_id`, ranked by combined score:

```sql
WITH q AS (SELECT plainto_tsquery('simple', $1) AS tsq)
-- 1) messages (best rank weight)
SELECT s.id, s.title, s.preview, s.last_active_at, s.title_source,
       'message' AS match_source,
       ts_rank(to_tsvector('simple', coalesce(m.text, '')), q.tsq) AS rank,
       ts_headline('simple', coalesce(m.text, ''), q.tsq,
                   'MaxFragments=1, MaxWords=20, MinWords=8') AS snippet
FROM messages m
JOIN sessions s ON s.id = m.thread_id, q
WHERE m.text IS NOT NULL
  AND to_tsvector('simple', m.text) @@ q.tsq

UNION ALL
-- 2) session metadata
SELECT s.id, …, 'metadata' AS match_source, …
FROM sessions s, q
WHERE to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(preview,'')) @@ q.tsq

UNION ALL
-- 3) archived session summaries
SELECT s.id, …, 'summary' AS match_source, …
FROM memory_session_summaries mss
JOIN sessions s ON s.id = mss.session_id, q
WHERE to_tsvector('simple', mss.summary) @@ q.tsq
```

Outer query: `DISTINCT ON (id) … ORDER BY id, rank DESC`, then order by
`rank DESC, last_active_at DESC LIMIT $2`.

Also accept `ILIKE '%query%'` as a fallback when `plainto_tsquery` returns empty
(single-char queries, punctuation-only input) — same pattern as contacts `get_by_name`.

Minimum query length: **2 characters**; shorter queries return `[]` without error.

### 3. History panel (ze-web)

```
┌─ History ─────────────────────────────┐
│ Past conversations                  │
├─────────────────────────────────────┤
│ 🔍 Search conversations…            │
├─────────────────────────────────────┤
│ [SessionRow — active]               │
│ [SessionRow — snippet highlighted]  │
│ …                                   │
└─────────────────────────────────────┘
```

- `SessionSearchInput` in `ChatSidePanel` history header (or `SessionList` top).
- Debounce 300 ms; cancel in-flight requests on new input.
- `q.length < 2` → `listSessions()` with infinite scroll (cursor via `next_before`).
- `q.length ≥ 2` → `searchSessions({ q })` — single page, no load-more in v1.
- Pass `snippet` + `matchSource` into `SessionRow`; render snippet with plain text
  (strip FTS `<b>` tags from `ts_headline` or map to styled `<mark>`).
- Match source pill: `message` · `summary` · `title` (map `metadata` → `title` in UI).

FSD placement:

| Slice | File |
|-------|------|
| `entities/session/api/` | `useSessionSearchQuery.ts` |
| `entities/session/ui/` | extend `SessionRow` |
| `widgets/chat-workspace/ui/` | `SessionSearchInput.tsx`, wire in `SessionList` |

---

## Interface Contract

### Public API changes

#### `GET /api/v0/sessions` (breaking shape change)

Replace bare `list[SessionSchema]` with a paginated envelope. Cursor key:
`last_active_at` (sessions are ordered recency-first, same invariant as today).

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 30 | Max sessions per page (cap 100) |
| `before` | datetime | now | Return sessions with `last_active_at` strictly older than this |

**Response:** `SessionListResponse`

```python
class SessionListResponse(BaseModel):
    items: list[SessionSchema]
    next_before: datetime | None   # pass as `before` to fetch the next page; None = end
```

Store change: `list_all(limit=50)` → `list_page(*, limit=30, before: datetime | None)`.

Tie-breaker: when multiple sessions share the same `last_active_at`, order by `id DESC`
and use composite cursor `(last_active_at, id)` if collisions appear in practice
(start with timestamp-only; add `before_id` param only if needed).

#### `GET /api/v0/sessions/search`

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | str | required | Search string (min 2 chars) |
| `limit` | int | 20 | Max results (cap 50) |

**Response:** `list[SessionSearchResult]`

```python
class SessionSearchResult(BaseModel):
    id: str
    title: str | None
    preview: str | None
    title_source: Literal["user", "generated"] | None
    created_at: datetime
    last_active_at: datetime
    match_source: Literal["message", "metadata", "summary"]
    snippet: str | None          # ts_headline excerpt; None for metadata-only hits
    rank: float
```

`operation_id`: `searchSessions`
`summary`: "Search chat sessions by message content and summaries"

#### `SessionSchema` extension

Add optional `title_source` to `SessionSchema` and `listSessions` responses (nullable for
pre-migration rows).

### WebSocket frames / events

None.

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| `q` shorter than 2 chars | `200` with `[]` |
| `plainto_tsquery` empty (punctuation only) | Fall back to `ILIKE` on messages + sessions title |
| No matches | `200` with `[]`; UI shows "No conversations found" |
| Title LLM call fails | Log warning; keep `title_source='user'` placeholder |
| Session has messages but no `sessions` row | Search still finds via messages JOIN; upsert on next activity heals row |
| Query contains `%` or `_` | Parameterized queries only; ILIKE fallback escapes wildcards |

---

## Data Structures

```python
# core/ze-core/ze_core/conversation/sessions/types.py

@dataclass
class Session:
    id: str
    title: str | None
    preview: str | None
    title_source: str | None   # 'user' | 'generated' | None
    created_at: datetime
    last_active_at: datetime


@dataclass
class SessionSearchHit:
    session: Session
    match_source: str          # 'message' | 'metadata' | 'summary'
    snippet: str | None
    rank: float
```

```python
# core/ze-core/ze_core/conversation/sessions/title.py

class SessionTitleGenerator:
    async def generate(self, *, user_text: str, assistant_text: str) -> str: ...
```

---

## Database Schema

See [Index strategy](#index-strategy) above. No new tables.

Existing rows: `title_source` defaults to `'user'` where `title IS NOT NULL`, else `NULL`.

---

## Migration / Rollout Notes

1. Apply `zc023` then `zm014` (order enforced via `depends_on` if needed; summaries index is independent).
2. Deploy API + web together (search endpoint + UI).
3. Title generation is forward-only; existing sessions retain first-message titles until user sends a new message (which won't re-trigger generation if `title_source != 'user'`). Optional backfill script out of scope.

Rollback: drop indexes + column; search endpoint removed; UI falls back to list-only.

---

## Configuration

```yaml
# apps/ze-api/config/config.yaml
models:
  session_title: anthropic/claude-haiku-4-5   # cheap, one-shot label
```

Wired in `ZeApiSettings` / container like other model slots.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `PostgresSessionStore` | `search()` + `title_source` column |
| `LLMClient` (OpenRouter) | Title generation |
| `memory_session_summaries` table | Archived session FTS |
| Phase 90 History panel | Search UI surface |

---

## Alternatives Considered

| Option | Why rejected |
|--------|-------------|
| Client-side filter of `listSessions` | Doesn't scale; no message-body search; 50-session cap |
| Embedding / semantic search only | Higher cost and latency for a history lookup; FTS is exact-match friendly |
| Search `memory_episodes` in v1 | Duplicates live `messages` for active sessions; summaries cover archived text |
| `'english'` tsconfig | Poor recall for non-English user content |
| Block reply until title generated | Violates Ze's non-blocking delivery model |
| Materialized `session_search_documents` view | Premature; union query sufficient at single-user scale |

---

## Testing Strategy

| Layer | What to cover | Approach |
|-------|--------------|----------|
| Unit | `SessionTitleGenerator` prompt + parse | Mock `LLMClient.complete`; assert ≤8 words, no quotes |
| Unit | `PostgresSessionStore.search` ranking | AsyncMock pool; fixture rows for message vs summary hit |
| Unit | `title_source` upsert logic | Assert generated title not overwritten by later user upsert |
| Integration | FTS end-to-end | Real Postgres (test container); insert messages, query search |
| API | `searchSessions` route | ze-api test: auth, min length, snippet shape |
| Web | `SessionList` search mode | vitest: debounce mock, empty vs results states |
| Web | `SessionRow` snippet render | vitest: headline tags stripped/styled |

---

## Definition of Done

- [ ] `title_source` column + FTS indexes migrated (`zc023`, `zm014`)
- [ ] `SessionTitleGenerator` + async hook in `turns.py` / `confirmation.py`
- [ ] `SessionStore.search()` with unit tests
- [ ] `GET /api/v0/sessions` cursor pagination + `SessionListResponse` (codegen breaking change)
- [ ] `GET /api/v0/sessions/search` + `SessionSearchResult` schema
- [ ] `make codegen` + `useSessionSearchQuery` + `useSessionsQuery` (infinite)
- [ ] History panel search input wired; browse mode infinite scroll; `SessionRow` shows snippets
- [ ] `title_source` exposed on `SessionSchema`
- [ ] Spec status → Done; `specs/README.md` row updated

---

## Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| FTS config | `'simple'` | Multilingual user base; no stemmer assumptions |
| Primary index target | `messages.text` | Authoritative transcript; always populated on turn |
| Archived content | `memory_session_summaries` only | Episodes redundant with messages for active sessions |
| Title timing | Once, after first assistant reply | Cheap; avoids re-titling complexity in v1 |
| Title overwrite | `title_source` flag | Preserve generated titles; distinguish legacy placeholders |
| List pagination | Cursor on `last_active_at` | Matches `GET /memory/feed`; stable under inserts |
| Empty search | Paginated `listSessions` | Browse and search are separate modes |
| Search pagination | Fixed `limit` (20, cap 50) | Ranked FTS fits on one screen; user refines query |
| Snippet delivery | `ts_headline` server-side | Consistent highlighting; client strips/maps tags |
| Cross-package SQL | Session store queries `memory_session_summaries` | Single-user DB; avoids new service layer for v1 |

---

## Implementation Notes

- Strip markdown from title-generation input (plain text only); store plain title.
- `ts_headline` returns `<b>…</b>` — frontend must not inject raw HTML; parse or strip tags.
- Invalidate `queryKeys.sessions` on session select / new chat; search queries keyed as `['sessions', 'search', q]`.
- Update `ChatNavGroup` to keep using the first page only (`limit=8` slice client-side or `limit=8` param) — no infinite scroll in nav.
- Breaking API change: any caller of `listSessions` must read `.items`; run codegen before merging web + API.

---

## Open Questions

- [x] ~~Title generation timing~~ — **Resolved:** once after first exchange (`title_source` gate).
- [x] ~~Include episodes in FTS?~~ — **Resolved:** summaries only for archived text; messages for live.
- [x] ~~FTS language config~~ — **Resolved:** `'simple'`.
- [x] ~~Empty query behaviour~~ — **Resolved:** fall back to paginated `listSessions` in UI; API returns `[]` for `q < 2`.
- [x] ~~Raise `listSessions` limit vs pagination?~~ — **Resolved:** cursor pagination on `listSessions` in this phase (do not bump the hard cap). Search stays single-page.
