# Contract: Open Loops REST API

Owned by `ze-api`, routes in `ze_api/api/routes/loops.py`, calling into
`ze_worldstate.rest`'s plain-dict service functions (mirrors `ze_automation/rest.py`'s
pattern). All routes require the existing single API key (`require_api_key`), prefixed
`/api/v0`, tagged `loops`. Every route declares `response_model`, `operation_id`, `summary`,
`description` per `CLAUDE.md`'s OpenAPI convention.

## GET /api/v0/loops

**operation_id**: `listLoops`

Lists all open loops (FR-014). Query params:

| Param | Type | Notes |
|---|---|---|
| `state` | optional string | Filter to one lifecycle state; omitted = all non-terminal states (`suspected`, `active`, `drifting`) |

**Response** `list[LoopListItem]`:

```json
[
  {
    "id": "uuid",
    "title": "Renew passport before the trip",
    "state": "suspected",
    "claim_kind": "suspicion",
    "provenance": "conversation",
    "confidence": 0.35,
    "created_at": "2026-07-21T10:00:00Z",
    "updated_at": "2026-07-21T10:00:00Z"
  }
]
```

`suspected` loops MUST be distinguishable from confirmed (`active`+) ones purely from `state` +
`confidence` in the response (FR-014) — no separate flag needed.

## GET /api/v0/loops/{loop_id}

**operation_id**: `getLoop`

Returns full detail for one loop, including its evidence links (for the "why does Ze think
this?" surface) and entity links.

**Response** `LoopDetail`:

```json
{
  "id": "uuid",
  "title": "Send Maria the contract",
  "state": "suspected",
  "claim_kind": "suspicion",
  "provenance": "conversation",
  "confidence": 0.35,
  "goal_id": null,
  "evidence": [
    {"type": "episode", "id": "uuid", "summary": "..."}
  ],
  "entities": [
    {"id": "uuid", "canonical_name": "Maria", "entity_type": "person"}
  ],
  "created_at": "2026-07-21T10:00:00Z",
  "updated_at": "2026-07-21T10:00:00Z"
}
```

**404** if `loop_id` does not exist (`LoopNotFoundError`).

## POST /api/v0/loops/{loop_id}/confirm

**operation_id**: `confirmLoop`

Transitions a `suspected` loop to `active` (FR-007, FR-015). Raises invalid-transition (409) if
the loop is not currently `suspected`.

**Response** `LoopTransitionResponse`: `{"id": "uuid", "state": "active", "confidence": 0.8}`

## POST /api/v0/loops/{loop_id}/close

**operation_id**: `closeLoop`

Transitions `active` or `drifting` → `closed` (done) (FR-015).

**Response** `LoopTransitionResponse`: `{"id": "uuid", "state": "closed", "confidence": ...}`

## POST /api/v0/loops/{loop_id}/drop

**operation_id**: `dropLoop`

Transitions any non-terminal state → `dropped` (not real / no longer relevant / dismiss)
(FR-007, FR-015). Records the evidence fingerprint so the same evidence does not resurface the
loop later (FR-011).

**Response** `LoopTransitionResponse`: `{"id": "uuid", "state": "dropped", "confidence": ...}`

---

## Internal contract: `ze_worldstate` public surface

Consumed by `ze-api`'s composition layer and by the inflow call sites (conversation turn
processing, `ze-messenger`, `ze-calendar`, ingestion) per FR-017's direct-write proto-contribution.

```python
# ze_worldstate/extraction.py
async def propose_loop_candidates(
    text: str,
    provenance: str,               # "conversation" | "email" | "calendar" | "ingestion" | "user_declared"
    evidence_refs: list[EvidenceRef],
    llm_client: LLMClient,
    embedder: Any,
    loop_store: LoopStore,
    entity_resolver: Any,          # ze-memory's existing resolution surface
) -> list[OpenLoop]:
    """Conservative, relevance-gated (FR-009). Returns [] for ordinary content."""

# ze_worldstate/decay.py
async def cascade_from_evidence(
    evidence_type: str,            # "fact" | "episode"
    evidence_id: UUID,
    loop_store: LoopStore,
) -> list[OpenLoop]:
    """Called synchronously by the evidence-writing code path (research.md §3)."""

# ze_worldstate/store.py
class LoopStore(Protocol):
    async def create(self, loop: OpenLoop) -> OpenLoop: ...
    async def get(self, loop_id: UUID) -> OpenLoop | None: ...
    async def list(self, states: list[str] | None = None) -> list[OpenLoop]: ...
    async def transition(self, loop_id: UUID, new_state: str) -> OpenLoop: ...
    async def link_entity(self, loop_id: UUID, entity_id: UUID) -> None: ...
    async def link_evidence(self, loop_id: UUID, evidence_type: str, evidence_id: UUID) -> None: ...
```

No breaking changes to any existing contract — `ze-memory`'s `GraphStore`/`GraphExpansion` gain
one additive bucket (`"open_loop"`); no existing route, store method, or schema field changes
shape.
