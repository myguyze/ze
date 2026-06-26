# Phase 88 — Memory Feed

**Status:** Done
**Depends on:** Phase 2 (Memory), Phase 45 (Native App Interface), Phase 82 (ze-web FSD)
**Packages touched:** `apps/ze-api`, `apps/ze-web`

---

## What this is

A reverse-chronological stream of everything Ze has retained about the user — facts and
episodes interleaved by creation time. The goal is to give the user continuous, ambient
proof that memory is working: "Ze remembers you said X", "Ze learned Y from a conversation".

This is the lowest-effort trust-building surface in the Brain UI suite. All data already
exists in `memory_facts` and `memory_episodes`; this phase is primarily a read endpoint and
a list UI.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Feed shape | Merged facts + episodes, reverse-chrono | Single scrollable stream is simpler than two separate tabs for a first view |
| Pagination | Cursor-based (`before` ISO timestamp) | Offset pagination is fragile under insertions during scroll |
| Endpoint location | `GET /api/v0/memory/feed` | Separate from `/digest` (which is a snapshot for the memory management UI) |
| Frontend location | Dedicated `/brain-memory` route | `ze-web` already has a `pages/` FSD structure; a dedicated page is discoverable |
| Filtering | Agent filter + type filter (`fact` / `episode`) on the backend | Filters apply uniformly to both facts and episodes |
| Inline actions | Confirm / reject / edit facts inline in the feed | `reviewFacts` POST endpoint now targets `memory_facts` (the active store) |
| Fact source table | `memory_facts` (ze-memory) | Active write target; `user_facts` (ze-core) is a zombie table no longer written to |
| Episode source table | `memory_episodes` (ze-memory) | Active write target; `episodes` (ze-core) is a zombie table no longer written to |
| `agent` on facts | `memory_facts.agent` column (zm012) | `Fact` dataclass gets `agent` field; extractor stamps agent at write time; consolidation uses `'consolidation'`, dream uses `'dream'` |
| `reviewFacts` retargeted | `memory_facts` instead of `user_facts` | Response model changed to `list[MemoryFeedItem]`; `user_facts` was already dead |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `GET /api/v0/memory/feed` endpoint | ✅ Done |
| Schema types in `schemas.py` | ✅ Done |
| Codegen update (`make codegen`) | ✅ Done |
| `pages/brain-memory/` FSD slice | ✅ Done |
| `MemoryFeedItem` component | ✅ Done |
| Inline fact review actions | ✅ Done |
| Nav entry via plugin UI manifest | ✅ Done (core nav route `brain-memory`) |
| `memory_facts.agent` column (zm012 migration) | ✅ Done |
| `Fact.agent` field + extractor write path | ✅ Done |
| `reviewFacts` retargeted to `memory_facts` | ✅ Done |

---

## REST API

### `GET /api/v0/memory/feed`

Returns a cursor-paginated list of memory events (facts and episodes) ordered newest first.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 50 | Max items per page |
| `before` | ISO datetime | now | Return items older than this timestamp |
| `type` | `fact` \| `episode` \| `all` | `all` | Filter by item type |
| `agent` | str | — | Filter by originating agent name |

**Response:**

```python
class MemoryFeedItem(BaseModel):
    id: UUIDType
    type: Literal["fact", "episode"]
    # fact-specific (None for episodes)
    key: str | None
    value: str | None
    confidence: float | None
    reviewed: bool | None
    contradicted: bool | None
    provenance: str | None           # "raw" | "synthesized"
    # episode-specific (None for facts)
    summary: str | None
    prompt_snippet: str | None       # first 120 chars of episode.prompt
    # shared
    agent: str
    created_at: datetime


class MemoryFeedResponse(BaseModel):
    items: list[MemoryFeedItem]
    next_before: datetime | None     # None when no more pages
    total_facts: int                 # total unfiltered fact count (for header stat)
    total_episodes: int              # total unfiltered episode count
```

**SQL (simplified):**

```sql
SELECT id, 'fact' AS type,
       predicate AS key, value, confidence, reviewed, contradicted,
       provenance, NULL AS summary, NULL AS prompt_snippet,
       agent, created_at
FROM memory_facts
WHERE created_at < $before
  AND ($agent IS NULL OR agent = $agent)
  AND ($type = 'all' OR $type = 'fact')

UNION ALL

SELECT id, 'episode' AS type,
       NULL, NULL, NULL, NULL, NULL,
       NULL, summary, LEFT(prompt, 120) AS prompt_snippet,
       agent, created_at
FROM memory_episodes
WHERE created_at < $before
  AND ($agent IS NULL OR agent = $agent)
  AND ($type = 'all' OR $type = 'episode')

ORDER BY created_at DESC
LIMIT $limit
```

> **Note:** `memory_facts.agent` was added via migration zm012. The `Fact` dataclass has
> `agent: str = "unknown"`. `gather_fact_proposals` stamps the routing agent name at extraction
> time. Consolidation writes use `'consolidation'`; dream synthesis uses `'dream'`.

**operation_id:** `getMemoryFeed`

---

## Frontend (`apps/ze-web`)

### Route

`/brain/memory` — dedicated page. Add to nav via `ZePlugin.ui_contributions()` on a
core-owned `BrainPlugin` (or wire directly to `nav-routes.ts` since Brain is not a
ZePlugin domain).

### FSD layout

```
pages/brain-memory/
  ui/
    BrainMemoryPage.tsx     # page shell, filter toolbar, infinite scroll
widgets/memory-feed/
  ui/
    MemoryFeed.tsx          # infinite scroll list via useInfiniteQuery
    MemoryFeedItem.tsx      # single row — fact or episode card
    FactReviewActions.tsx   # confirm / reject / edit buttons (reuses reviewFacts)
```

### Component behaviour

- **Header stats bar:** "N facts · M episodes" pulled from `total_facts` / `total_episodes`.
- **Filter bar:** type toggle (All / Facts / Episodes), agent dropdown, search (client-side
  filter on `key`/`value`/`summary`).
- **Fact row:** shows `key: value`, confidence pill, provenance badge. Contradicted facts
  get a strikethrough and warning color. Unreviewed facts show confirm/reject/edit inline.
- **Episode row:** shows agent badge, `summary` (or `prompt_snippet` if no summary yet),
  relative timestamp.
- **Infinite scroll:** `useInfiniteQuery` with `getNextPageParam` returning
  `next_before`; fires when the user scrolls to within 200 px of the bottom.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `memory_facts` table | Source of fact items |
| `memory_episodes` table | Source of episode items |
| `GET /api/v0/memory/facts/review` (`reviewFacts`) | Inline fact curation from feed |
| `@ze/client` codegen | Typed `getMemoryFeed` SDK method |
| TanStack Query `useInfiniteQuery` | Cursor pagination in React |

---

## Out of scope

- Writing or editing facts from the feed (review-only).
- Searching by semantic similarity (separate future phase).
- Dream/synthesis feed items (those live in the dream log — Phase 78 UI).
- Real-time push updates when new facts are written (polling on focus is sufficient).

---

## Testing

| Area | Tests |
|------|-------|
| `GET /api/v0/memory/feed` | Returns merged + sorted items; cursor pagination; type + agent filters |
| `MemoryFeedItem` | Renders fact and episode variants; review actions fire `reviewFacts` |
| Infinite scroll | `useInfiniteQuery` advances cursor on scroll trigger |
