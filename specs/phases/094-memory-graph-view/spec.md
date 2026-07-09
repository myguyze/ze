# Phase 94 — Memory Graph View

**Status:** Done
**Depends on:** Phase 88 (Memory Feed — establishes `/brain/memory` route), Phase 57 (Correlation engine — graph store)
**Packages touched:** `core/ze-memory`, `apps/ze-api`, `apps/ze-web`

---

## What this is

An interactive node graph that visualises the entities Ze has extracted from memory
(people, places, organisations, topics) and the relationships between them. The user
can click a node to see its linked facts, episodes, and neighbouring entities. This
makes the abstract memory graph tangible and browsable.

The data source is the existing `memory_entities` and `memory_relationships` tables
(populated since Phase 57). No new schema is required — this phase is a read-only
visualisation layer on top of existing data.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph traversal | `PostgresGraphStore.expand()` (already exists) with `max_hops=1` | Correct tool; backend already does neighbourhood expansion |
| Initial graph load | Top-50 entities by relationship count | Avoids overwhelming the user; the most-connected nodes are most interesting |
| Frontend graph library | `@xyflow/react` (React Flow, MIT) | Force-directed layout, declarative React API, actively maintained |
| Node types | `entity` (person/place/org/topic) | Relationship nodes are edges, not nodes, in this visualisation |
| Edge labels | `predicate` from `memory_relationships` | e.g. "works_at", "located_in", "knows" |
| Click-to-expand | Click a node → `expand()` call with that entity as seed | Progressive disclosure; prevents loading the full graph upfront |
| Detail panel | Right sidebar shows entity detail (facts, episodes, attrs) on node select | Same split-pane pattern as Phase 90 |
| Search | Text search box that highlights matching nodes; doesn't re-fetch | Client-side filter on loaded nodes |
| Layout algorithm | `dagre` auto-layout as initial positioning; user can drag nodes | Dagre gives a readable starting layout; free drag is essential for personal graphs |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `GET /api/v0/memory/graph` endpoint | ✅ Done |
| `GET /api/v0/memory/graph/entity/{entity_id}` detail endpoint | ✅ Done |
| Schema types | ✅ Done |
| Codegen update | ✅ Done |
| `pages/brain-graph/` FSD slice | ✅ Done |
| `MemoryGraph` component (React Flow) | ✅ Done |
| `EntityDetailPanel` sidebar | ✅ Done |
| Node search | ✅ Done |

---

## REST API

### `GET /api/v0/memory/graph`

Returns the initial graph: top-N entities by relationship count, plus all edges
between them.

**Query params:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 50 | Max entities to return |
| `entity_type` | str | — | Filter by entity type (person, place, org, topic) |
| `seed_id` | UUID | — | If set, expand from this entity (max_hops=1) |

**SQL for initial load (top entities by degree):**

```sql
SELECT e.id, e.entity_type, e.canonical_name, e.aliases, e.attrs,
       COUNT(r.id) AS degree
FROM memory_entities e
LEFT JOIN memory_relationships r
  ON r.source_id = e.id OR r.target_id = e.id
GROUP BY e.id
ORDER BY degree DESC
LIMIT $limit
```

Edges: all `memory_relationships` where both `source_id` and `target_id` are in the
returned entity set.

**Response:**

```python
class GraphEntityNode(BaseModel):
    id: UUIDType
    entity_type: str          # "person" | "place" | "org" | "topic" | …
    canonical_name: str
    aliases: list[str]
    attrs: dict               # JSONB attrs from memory_entities
    degree: int               # total edge count (for node sizing)

class GraphEdge(BaseModel):
    id: UUIDType
    source_id: UUIDType
    target_id: UUIDType
    predicate: str
    confidence: float

class MemoryGraphResponse(BaseModel):
    nodes: list[GraphEntityNode]
    edges: list[GraphEdge]
```

- **operation_id:** `getMemoryGraph`

### `GET /api/v0/memory/graph/entity/{entity_id}`

Detail for a selected entity: facts, episodes, and 1-hop neighbours not already in
the current graph (for expand-on-click).

```python
class EntityDetailResponse(BaseModel):
    entity: GraphEntityNode
    facts: list[FactDigestItem]      # reuse Phase 88 schema
    episodes: list[EpisodeDigestItem]  # reuse Phase 88 schema
    neighbours: list[GraphEntityNode]  # 1-hop entities (for expand)
    neighbour_edges: list[GraphEdge]   # edges connecting neighbours to this node
```

- **operation_id:** `getEntityDetail`
- **404** when entity not found.

---

## Frontend (`apps/ze-web`)

### Route

`/brain/graph`

### FSD layout

```
pages/brain-graph/
  ui/
    BrainGraphPage.tsx        # layout: graph + search toolbar + detail panel
widgets/memory-graph/
  ui/
    MemoryGraph.tsx           # React Flow wrapper with Ze node/edge types
    EntityNode.tsx            # custom node: icon + name + degree badge
    EntityDetailPanel.tsx     # right sidebar with facts, episodes, expand button
    GraphSearchBar.tsx        # text input → highlight matching nodes
    GraphToolbar.tsx          # zoom controls, layout reset, entity_type filter
```

### Node design

Each node:
- **Icon** based on `entity_type` (person = user icon, place = map-pin, org = building, topic = hash).
- **Label** = `canonical_name` (truncated to 20 chars).
- **Size** scales with `degree` (min 40 px, max 80 px radius).
- **Color** by entity type (consistent with `AGENT_COLORS` pattern but for entity types).

### Edge design

- Thin gray lines; label = `predicate` shown on hover.
- Confidence < 0.5 rendered as dashed.

### Interaction flow

1. Page loads → `getMemoryGraph` → render initial graph with dagre layout.
2. User clicks a node → `getEntityDetail` → right panel slides open with facts +
   episodes. An "Expand" button loads `neighbours` + `neighbour_edges` and merges them
   into the React Flow graph state.
3. Expanded nodes appear with a subtle pulse animation on first render.
4. User can drag nodes to reposition. "Reset layout" button re-runs dagre.
5. Search bar filters `canonical_name` and `aliases` client-side; matching nodes get a
   highlight ring; non-matching nodes dim.

### Entity detail panel

```
┌──────────────────────────────────────┐
│  👤 João Matos                       │
│  person  •  12 connections           │
├──────────────────────────────────────┤
│  Facts about this entity (4)         │
│  • works_at: Anthropic               │
│  • located_in: Lisbon                │
│  • interest: AI systems              │
├──────────────────────────────────────┤
│  Episodes mentioning this entity (7) │
│  • "Discussed collaboration on…"    │
│  • "User mentioned meeting…"         │
├──────────────────────────────────────┤
│  [+ Expand 3 neighbours]             │
└──────────────────────────────────────┘
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `memory_entities` table | Graph nodes |
| `memory_relationships` table | Graph edges |
| `PostgresGraphStore.expand()` | Neighbourhood expansion |
| `memory_facts`, `memory_episodes` | Entity detail panel content |
| `@xyflow/react` (React Flow) | Force-directed graph rendering |
| `dagre` | Initial auto-layout |
| `GET /api/v0/memory/graph` | Initial graph load |
| `GET /api/v0/memory/graph/entity/{id}` | Node detail + expand |

---

## Out of scope

- Editing entity names or merging duplicate entities from the UI.
- Filtering edges by predicate type (future enhancement; filter bar can add this).
- Full-graph export (JSON/PNG) — straightforward to add post-ship.
- Semantic search across entity names (uses embeddings — separate phase).
- Showing relationship confidence as edge thickness (visual polish; deferred).

---

## Testing

| Area | Tests |
|------|-------|
| `getMemoryGraph` | Returns top-N entities + in-set edges; entity_type filter; seed_id expansion |
| `getEntityDetail` | Returns facts, episodes, 1-hop neighbours; 404 for unknown id |
| `MemoryGraph` | Renders nodes and edges from mock data; click fires entity detail fetch |
| Expand | Merges neighbour nodes/edges into graph without duplicates |
| Search | Highlights matching nodes; dims others |
| `EntityDetailPanel` | Renders facts, episodes, expand button |
