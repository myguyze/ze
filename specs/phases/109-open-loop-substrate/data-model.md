# Phase 1 Data Model: Open-Loop Substrate

## Entity: OpenLoop

Owned by `ze-worldstate`, table `open_loops` (migration `zw001_open_loops.py`).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, PK | |
| `title` | TEXT, NOT NULL | Human-readable description (FR-001) |
| `state` | TEXT, NOT NULL, default `'suspected'` | One of `suspected`/`active`/`drifting`/`closed`/`dropped` (FR-002) — `TEXT` + a Python `LoopState` enum, not a Postgres `ENUM` type, to match the codebase's `TEXT`-column convention (see `memory_relationships.source_type`) |
| `claim_kind` | TEXT, NOT NULL | `identity`/`fact`/`inference`/`suspicion`/`priority` — first code instance of the doctrine's taxonomy (Clarification); loops are typically `suspicion` (inferred) or a commitment-equivalent kind when `user_declared` |
| `provenance` | TEXT, NOT NULL | `conversation`/`email`/`calendar`/`ingestion`/`user_declared`/… (FR-003) |
| `confidence` | REAL, NOT NULL, `CHECK (confidence >= 0.0 AND confidence <= 1.0)` | Continuous float 0.0–1.0 (Clarification); decays via `ze_worldstate/decay.py` (FR-004) |
| `goal_id` | UUID, NULL, FK → `goals.id` (no cascade delete; loops and goals are parallel — FR-016) | Optional reference only; never required |
| `dismissed_evidence_fingerprint` | TEXT, NULL | Stable hash of the evidence that led to a `dropped` state, used to satisfy FR-011 (do not resurface from evidence the user already dismissed) without needing to keep full evidence rows around once a loop is dropped |
| `created_at` | TIMESTAMPTZ, NOT NULL, default `now()` | |
| `updated_at` | TIMESTAMPTZ, NOT NULL, default `now()` | |
| `confirmed_at` | TIMESTAMPTZ, NULL | Set on `suspected → active` transition |
| `closed_at` | TIMESTAMPTZ, NULL | Set on transition to `closed` or `dropped` |

### Validation rules

- `state` transitions permitted in Phase A: `suspected → active` (confirm), `suspected →
  dropped` (dismiss), `active → closed` (done), `active → dropped` (no longer relevant),
  `active → drifting` **not implemented in Phase A** (Phase B), `drifting → closed | dropped`
  (manual, in case a user closes a drifting loop directly — the state must exist as a valid target
  even though nothing produces it automatically yet, per FR-002).
- `provenance = "user_declared"` loops MUST be created directly in `state = "active"` with
  `confidence` at the high end of the range (FR-006) and no confirmation step.
- All other provenances MUST be created in `state = "suspected"` at low confidence (FR-005).
- Closing/dropping a loop never deletes rows in `memory_entities`/`memory_facts`/`memory_episodes`
  (FR-013) — only `open_loops.state` and the `memory_relationships` rows scoped to that loop's
  `source_id`/`target_id` are affected, never the referenced entities/evidence themselves.

## Entity: LoopClaimKind (enum, code-only — no separate table)

Defined in `ze_worldstate/types.py`, values fixed to `ze-doctrine.md`'s epistemic ontology:
`identity`, `fact`, `inference`, `suspicion`, `priority`. First implementation of this taxonomy
in code (Clarification); the future contribution seam (`contribution-seam.md`) is expected to
import this same enum rather than the loop layer migrating to a new one later.

## Entity: LoopState (enum, code-only — no separate table)

`suspected`, `active`, `drifting`, `closed`, `dropped` (FR-002).

## Relationship: Loop ↔ Entity link

**No new table.** A row in the existing `memory_relationships` table (owned by `ze-memory`,
`zm003_relationships.py`):

| Column | Value for a loop↔entity link |
|---|---|
| `source_type` | `"entity"` |
| `source_id` | the `memory_entities.id` |
| `predicate` | `"has_open_loop"` |
| `target_type` | `"open_loop"` (new value; column is unconstrained `TEXT`) |
| `target_id` | the `open_loops.id` |
| `confidence` | entity-resolution confidence (independent of the loop's own confidence) |
| `provenance_id` | the evidence (fact/episode) that established the link, if any |

Traversing an entity's neighbourhood via `GraphStore.expand()` reaches the loop (SC-004) once a
generic `"open_loop"` bucket is added to `_TYPE_BUCKET` (`ze_memory/graph/store.py`) and
`GraphExpansion` (`ze_memory/graph/types.py`) — a generic graph-substrate addition, not
domain-specific knowledge added to `ze-memory` (see research.md §2).

## Relationship: Loop ↔ Evidence link

**No new table.** A row in `memory_relationships`:

| Column | Value for a loop↔evidence link |
|---|---|
| `source_type` | `"open_loop"` |
| `source_id` | the `open_loops.id` |
| `predicate` | `"derived_from"` |
| `target_type` | `"fact"` or `"episode"` (existing bucket types) |
| `target_id` | the `memory_facts.id` or `memory_episodes.id` |

Enables: cascade retraction (FR-004 — `ze_worldstate.decay.cascade_from_evidence` looks up loops
by `target_id` = the retracted fact/episode id, `target_type` matching, `source_type =
"open_loop"`), and the review surface's "why does Ze think this?" transparency (FR-001's
"links to the evidence it was derived from").

## State machine

```
                 ┌──────────────┐
   (inferred)    │              │  confirm
   perception ──►│  suspected   ├──────────────► active ──► closed
   proposes      │              │                  │  │
                 └──────┬───────┘                  │  └────────► dropped
                        │ dismiss                   │
                        ▼                           │ (Phase B: automatic,
                     dropped                         │  not built here)
                                                     ▼
                                                  drifting ──► closed | dropped
                                                             (manual only in Phase A)

   (user_declared)
   user states ─────────────────────────────► active (direct entry, FR-006)
   directly
```

## Errors (`ze_worldstate/errors.py`)

- `LoopNotFoundError(ZeError)` — unknown loop id on a transition/read request.
- `InvalidLoopTransitionError(ZeError)` — attempted transition not permitted from the loop's
  current state (e.g. confirming an already-`active` loop).
