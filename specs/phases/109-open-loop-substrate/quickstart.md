# Quickstart: Validating the Open-Loop Substrate

Prerequisites: `make db-up`, `make migrate` (after `zw001_open_loops.py` lands), `make dev`
(backend running on `:8000`).

Each scenario below maps directly to a User Story / Success Criterion in `spec.md`.

## 1. Inferred loop is captured as a suspicion (User Story 1, SC-001, SC-002)

Send a conversation turn implying a commitment:

```bash
curl -X POST localhost:8000/api/v0/messages -H "Authorization: Bearer $ZE_API_KEY" \
  -d '{"text": "I really need to renew my passport before the trip"}'
```

Then:

```bash
curl localhost:8000/api/v0/loops -H "Authorization: Bearer $ZE_API_KEY"
```

**Expected**: a loop titled around "renew passport", `"state": "suspected"`,
`"provenance": "conversation"`, `"confidence"` in the low range (e.g. < 0.5), and no goal was
created as a side effect (check `GET /api/v0/goals` is unaffected).

## 2. User-declared loop is trusted immediately (User Story 2, SC-002)

```bash
curl -X POST localhost:8000/api/v0/messages -H "Authorization: Bearer $ZE_API_KEY" \
  -d '{"text": "remind me I need to follow up with the accountant next week"}'
curl localhost:8000/api/v0/loops -H "Authorization: Bearer $ZE_API_KEY"
```

**Expected**: a loop with `"state": "active"` directly (no `suspected` step),
`"provenance": "user_declared"`, high confidence.

Then say "I followed up with the accountant, it's done" and re-list — expect `"state": "closed"`.

## 3. Loop links into the existing entity graph (User Story 3, SC-004)

Prerequisite: a contact "Maria" already exists (`GET /api/v0/contacts`).

```bash
curl -X POST localhost:8000/api/v0/messages -H "Authorization: Bearer $ZE_API_KEY" \
  -d '{"text": "I told Maria I would send the contract this week"}'
curl localhost:8000/api/v0/loops/{loop_id} -H "Authorization: Bearer $ZE_API_KEY"
```

**Expected**: `LoopDetail.entities` contains the existing Maria entity id (not a new one). Then
fetch that entity's memory-graph neighbourhood (`GET /api/v0/memory/graph?entity_id=...` per
Phase 94) and confirm the loop appears as a reachable neighbour.

## 4. Review and lifecycle management (User Story 4, SC-003)

With a mix of `suspected`/`active` loops present:

```bash
curl localhost:8000/api/v0/loops -H "Authorization: Bearer $ZE_API_KEY"
# confirm one:
curl -X POST localhost:8000/api/v0/loops/{id}/confirm -H "Authorization: Bearer $ZE_API_KEY"
# drop another:
curl -X POST localhost:8000/api/v0/loops/{id}/drop -H "Authorization: Bearer $ZE_API_KEY"
# re-list and verify persistence:
curl localhost:8000/api/v0/loops -H "Authorization: Bearer $ZE_API_KEY"
```

**Expected**: state changes persist across the re-list call; dropped/closed loops no longer
appear among default (non-terminal) filtered results.

Web UI: `apps/ze-web`'s `LoopReviewList` widget should show the same data with a visibly
distinct treatment for `suspected` vs `active` rows.

## 5. Edge cases

- **Duplicate capture**: send two different inflows implying the same loop (e.g. a
  conversation mention and, if `ze-messenger` is wired, an email thread) about the same
  entity/topic; verify only one loop exists afterward with two evidence links, not two loops.
- **Dismissed-then-re-implied**: drop a loop, then resend the same triggering text; verify no
  new loop is created (FR-011).
- **Stale suspicion decay**: (requires either waiting ~14 days or invoking the
  `stale_suspicion` proactive job directly in a test/dev shell) verify an unconfirmed
  `suspected` loop transitions to `dropped` after the window.
- **Evidence retraction cascade** (SC-006): contradict or expire the fact/episode a loop cites
  (e.g. via the existing memory consolidation contradiction path) and re-fetch the loop —
  confidence must have measurably dropped.
- **Noise pressure** (SC-005): send several ordinary conversational turns with no real
  commitment ("what's the weather like", "thanks!") and verify `GET /api/v0/loops` gains no new
  rows.

## Automated coverage

The above scenarios should each have a corresponding test in
`core/ze-worldstate/tests/` (unit, mocked asyncpg/LLM/embedder) plus at least one
`apps/ze-api/tests/` integration-style test exercising the REST contract end-to-end. Web-side
coverage: `apps/ze-web/src/entities/loop` and `widgets/loop-review` via vitest.
