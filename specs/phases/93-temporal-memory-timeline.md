# Phase 93 — Temporal Memory Timeline

**Status:** Done
**Depends on:** Phase 88 (Memory Feed — establishes `/brain/memory` route and feed components)
**Packages touched:** `apps/ze-api`, `apps/ze-web`

---

## What this is

A horizontal date scrubber on the Memory Feed page that lets the user ask: *"What did
Ze know about me on this date?"* Dragging the scrubber to any point shows only the
facts and episodes that existed at that moment — giving a time-travel view of Ze's
accumulated knowledge.

This is useful for debugging (why did Ze give that answer last month?) and for
building user trust (the memory is a growing, durable record, not a black box that
forgets everything).

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Temporal filter | `as_of` query param on `GET /api/v0/memory/feed` (extend Phase 88) | Reuses the existing endpoint; no new route needed |
| Fact snapshot logic | `created_at <= as_of AND (expires_at IS NULL OR expires_at > as_of) AND NOT contradicted_before(as_of)` | Approximates what Ze "knew" at a point in time |
| Contradiction at-point | Skip facts with a contradicting fact created before `as_of` | Requires join on `memory_facts` self to find contradictions; acceptable complexity |
| Episode filter | `created_at <= as_of` | Episodes are append-only; no expiry logic |
| Scrubber granularity | Day | Finer granularity is rarely useful and adds UI complexity |
| Scrubber range | First fact/episode date → today | Computed from `GET /api/v0/memory/timeline-bounds` |
| Scrubber placement | Above the feed, below the filter bar (Phase 88) | Visible without scrolling; follows filter-then-browse pattern |
| "Now" mode | Default state; scrubber snaps back to today button | Avoids confusion when users close and reopen the page |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `as_of` param on `GET /api/v0/memory/feed` | ✅ Done |
| `GET /api/v0/memory/timeline-bounds` endpoint | ✅ Done |
| Schema updates | ✅ Done |
| Codegen update | ✅ Done |
| `TimelineScrubber` component | ✅ Done |
| `as_of` integration with Phase 88 feed | ✅ Done |
| "Now" snap button | ✅ Done |

---

## REST API changes

### Extend `GET /api/v0/memory/feed` (Phase 88)

Add optional query param:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `as_of` | ISO datetime | now | Return only items that existed at this point |

When `as_of` is set:
- Facts: `created_at <= as_of AND (expires_at IS NULL OR expires_at > as_of)`
  and exclude facts contradicted by another fact with `created_at <= as_of`.
- Episodes: `created_at <= as_of`.
- The response `total_facts` / `total_episodes` reflect the `as_of`-filtered counts.

**Contradiction exclusion (simplified SQL):**

```sql
-- Exclude facts contradicted before as_of
AND id NOT IN (
    SELECT DISTINCT f2.id
    FROM memory_facts f2
    WHERE f2.contradicted = true
      AND f2.updated_at <= $as_of
)
```

Note: `memory_facts.contradicted` is set when a contradiction is detected during
write-time NLI (Phase 79). The `updated_at` column records when the flag was set.
This is an approximation — it does not reconstruct the exact in-flight state — but
it is sufficient for the "time-travel memory" use case.

### New: `GET /api/v0/memory/timeline-bounds`

Returns the earliest and latest memory timestamps, used to configure the scrubber range.

```python
class TimelineBoundsResponse(BaseModel):
    earliest: datetime | None    # None when no memory items exist
    latest: datetime             # always now() on the server
```

- **operation_id:** `getMemoryTimelineBounds`

---

## Frontend (`apps/ze-web`)

### Placement

The `TimelineScrubber` is inserted between the filter bar and the feed list inside
`BrainMemoryPage` (Phase 88). It is only rendered once `timeline-bounds` has resolved
and `earliest` is not null.

### FSD layout

```
widgets/timeline-scrubber/
  ui/
    TimelineScrubber.tsx      # date slider + "Now" button + date label
```

### `TimelineScrubber` component

```typescript
interface TimelineScrubberProps {
  earliest: Date;
  value: Date | null;          // null = "Now" mode
  onChange: (d: Date | null) => void;
}
```

- Renders an `<input type="range">` with `min=earliest.getTime()` and
  `max=Date.now()`.
- Displays the selected date as "MMM D, YYYY" above the slider.
- "Now" button (visible only when `value !== null`) snaps back to live mode.
- The parent (`BrainMemoryPage`) passes `as_of` to the feed query when `value` is
  non-null.

### Feed integration

`BrainMemoryPage` uses `useInfiniteQuery` for the feed. The `as_of` param is threaded
into the query key:

```typescript
const { data, fetchNextPage } = useInfiniteQuery({
  queryKey: ["memory-feed", filters, asOf],
  queryFn: ({ pageParam = undefined }) =>
    client.getMemoryFeed({ ...filters, asOf, before: pageParam }),
  getNextPageParam: (last) => last.next_before ?? undefined,
});
```

When `as_of` changes (scrubber move), the query key changes and TanStack Query
re-fetches from the first page.

### Visual state

When a past `as_of` is active:
- A yellow banner reads "Viewing Ze's memory as of [date] — [N days ago]".
- The filter bar is disabled (scrubber-filtered results, not live).
- Feed items show only items that existed at the selected date.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Phase 88 `GET /api/v0/memory/feed` | Extended with `as_of` |
| `memory_facts.contradicted`, `memory_facts.updated_at` | Contradiction-before-date logic |
| `memory_facts.expires_at` | Expiry-before-date logic |
| `GET /api/v0/memory/timeline-bounds` | Scrubber range init |
| TanStack Query | Re-fetch on `as_of` change |

---

## Out of scope

- Per-hour granularity on the scrubber.
- Diffing memory between two dates ("what changed between X and Y?").
- Reconstructing the exact `AgentContext` Ze had at a given moment (would require
  storing retrieval snapshots — a much higher cost feature).

---

## Testing

| Area | Tests |
|------|-------|
| `GET /api/v0/memory/feed?as_of=` | Returns only pre-existing facts; excludes expired and contradicted |
| `GET /api/v0/memory/timeline-bounds` | Returns earliest created_at; null when empty |
| `TimelineScrubber` | Fires `onChange` on slide; "Now" button clears value |
| Feed re-fetch | Query key changes on scrubber move |
| Yellow banner | Visible when as_of is in the past |
