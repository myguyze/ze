# Phase 92 — Agent Activity Heatmap

**Status:** Pending
**Depends on:** Phase 89 (Message Trace — adds `trace` column to `messages`)
**Packages touched:** `apps/ze-api`, `apps/ze-web`

---

## What this is

A calendar heatmap showing how the user has been using Ze over time — which agents
handled their requests each day, and how many interactions each agent received. The
view gives a peripheral "at a glance" picture of Ze usage patterns: heavy research
days, calendar-heavy weeks, prospecting campaigns, etc.

The data source is the `messages.trace` column added in Phase 89 (JSONB with `agent`
field). No new data capture is needed; this phase is pure aggregation + visualization.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Aggregation | Backend SQL (`GROUP BY date, agent`) | Aggregation at scale belongs in Postgres, not JS |
| Time range | Rolling 12 months, fixed bucket `day` | A year of history is the natural mental model for a heatmap |
| Granularity | Day (not hour/week) | Day strikes the right balance — week hides variation, hour is too noisy |
| Color encoding | Per-agent color (matching existing agent badge colors) + intensity by count | Dual encoding: hue = agent type, intensity = volume |
| Multi-agent days | Stack top-3 agents by count; show total on hover | Most days are dominated by one agent; stacking covers the compound case |
| Library | `@uiw/react-heat-map` (MIT, zero extra deps) | Lightweight, customizable, already used in similar OSS dashboards |
| Placement | Dedicated `/brain/activity` route + nav entry | Avoids cluttering the goals or memory pages |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `GET /api/v0/activity/heatmap` endpoint | 🔲 Pending |
| Schema types | 🔲 Pending |
| Codegen update | 🔲 Pending |
| `pages/brain-activity/` FSD slice | 🔲 Pending |
| `AgentHeatmap` component | 🔲 Pending |
| `ActivityDayDetail` tooltip/popover | 🔲 Pending |

---

## REST API

### `GET /api/v0/activity/heatmap`

Returns per-day, per-agent message counts for the last 12 months (or a custom range).

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `start` | ISO date | 12 months ago | Start of range (inclusive) |
| `end` | ISO date | today | End of range (inclusive) |

**SQL:**

```sql
SELECT
    date_trunc('day', created_at AT TIME ZONE 'UTC') AS day,
    trace->>'agent'                                   AS agent,
    COUNT(*)                                          AS count
FROM messages
WHERE role = 'assistant'
  AND trace IS NOT NULL
  AND created_at >= $1
  AND created_at < $2 + INTERVAL '1 day'
GROUP BY 1, 2
ORDER BY 1 ASC, 3 DESC
```

**Response:**

```python
class AgentDayCount(BaseModel):
    agent: str
    count: int

class HeatmapDay(BaseModel):
    date: str                     # ISO date "YYYY-MM-DD"
    total: int
    agents: list[AgentDayCount]   # sorted desc by count

class ActivityHeatmapResponse(BaseModel):
    days: list[HeatmapDay]
    agents: list[str]             # all agent names seen in range (for legend)
    start: str
    end: str
```

- **operation_id:** `getActivityHeatmap`
- Empty `days` list when no messages in range (not 404).

---

## Frontend (`apps/ze-web`)

### Route

`/brain/activity`

### FSD layout

```
pages/brain-activity/
  ui/
    BrainActivityPage.tsx     # date range picker + heatmap + legend
widgets/agent-heatmap/
  ui/
    AgentHeatmap.tsx          # wraps @uiw/react-heat-map with Ze data
    HeatmapLegend.tsx         # agent color swatches + names
    DayDetailPopover.tsx      # on-hover: date, total, per-agent breakdown bar
```

### Visual design

```
                      Jun          Jul          Aug
Mon  [ ][ ][ ][ ][ ][ ][ ][ ][ ][ ][ ][ ][ ][ ]
Wed  [ ][ ][■][ ][■][ ][ ][▪][ ][ ][■][ ][ ][ ]
Fri  [ ][▪][▪][■][ ][ ][▪][■][▪][ ][■][▪][ ][ ]

■ companion (blue)    ▪ research (amber)    ░ calendar (green)
```

Each cell is colored by the dominant agent for that day; intensity encodes total
message count (light → 1–2, medium → 3–5, dark → 6+).

### Hover popover (`DayDetailPopover`)

```
Tuesday, 17 Jun
─────────────────
companion    ████████  5
research     ████      3
calendar     █         1
─────────────────
Total: 9 messages
```

A small horizontal bar chart per agent, absolute counts.

### Date range picker

Default: last 12 months. User can select a preset (3M / 6M / 12M / YTD) or a custom
date range. Changing the range re-fetches `getActivityHeatmap`.

### Agent color map

Shared `AGENT_COLORS` constant in `shared/config/agents.ts`:

```typescript
export const AGENT_COLORS: Record<string, string> = {
  companion:    "#3b82f6",  // blue
  research:     "#f59e0b",  // amber
  calendar:     "#10b981",  // green
  messenger:    "#8b5cf6",  // violet
  workflow:     "#06b6d4",  // cyan
  prospecting:  "#ef4444",  // red
};
```

Unknown agents fall back to `#6b7280` (gray).

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `messages.trace` column (Phase 89) | `trace->>'agent'` extraction |
| `@uiw/react-heat-map` | Calendar heatmap rendering |
| `GET /api/v0/activity/heatmap` | Aggregated data |
| `AGENT_COLORS` constant | Consistent color encoding across Brain UI |

---

## Out of scope

- Hour-level granularity or weekly rollups (day is sufficient for v1).
- Filtering by specific agent in the heatmap (use the legend to identify; drilldown is
  a future enhancement).
- Messages before Phase 89 ship (trace is null; those days show as empty cells).

---

## Testing

| Area | Tests |
|------|-------|
| `GET /api/v0/activity/heatmap` | Correct aggregation with multi-agent days; empty range; date boundary |
| `AgentHeatmap` | Renders cells with correct color for dominant agent |
| `DayDetailPopover` | Shows all agents for a multi-agent day |
| Date range picker | Re-fetches on preset/custom change |
