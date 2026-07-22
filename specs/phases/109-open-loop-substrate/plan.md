# Implementation Plan: Open-Loop Substrate

**Branch**: `109-open-loop-substrate` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Add the **open loop** as a first-class primitive: a new core package `ze-worldstate` holding
loops with honest provenance, continuous confidence (0.0–1.0), and a `suspected → active →
drifting → closed | dropped` lifecycle (Phase A implements every transition except the
automatic `active → drifting` detection, which is Phase B). Loops are captured two ways —
inferred from perception (starts `suspected`, needs confirmation) and user-declared (starts
`active`, trusted immediately) — and link into the *existing* memory graph (`ze-memory`'s
`memory_relationships` / `GraphStore`) rather than owning a parallel entity/evidence model, so
a loop is a projection of the world-state, not a fourth silo. `ze-worldstate` is wired directly
into `ze-api` the same way `ze-automation` is (a core package, not a `ZePlugin`, since it is
part of the constitutional spine, not a domain extension). Extraction is a direct write for now
(FR-017's proto-contribution), invoked from the same points that already write facts/episodes
for conversation, email, calendar, and ingestion inflows.

## Technical Context

**Language/Version**: Python 3.11 (matches the rest of the monorepo)

**Primary Dependencies**: `asyncpg` (Postgres I/O), `ze-agents` (logging/errors/dataclass
conventions), `ze-proactive` (stale-suspicion sweep job, per Clarification), `ze-memory`
(entity resolution, `GraphStore`/`memory_relationships` reuse, embedder-agnostic similarity
plumbing), `ze-data` (`DataDomain` export/delete), `ze-components` (server-driven UI tree for
the review surface, matching the contacts pattern)

**Storage**: PostgreSQL via `asyncpg`, one new Alembic chain (prefix `zw`) owned by
`ze-worldstate`; loop↔entity and loop↔evidence links are rows in the *existing*
`memory_relationships` table (no new join table) — see [data-model.md](./data-model.md)

**Testing**: `pytest` with `asyncio_mode = "auto"`, `AsyncMock` for asyncpg pools, no real DB/LLM
in unit tests, following `docs/testing.md`

**Target Platform**: Linux server (existing `ze-api` deployment; FastAPI/uvicorn)

**Project Type**: Backend package addition within the existing monorepo — new `core/ze-worldstate`
package + `ze-api` wiring + minimal `ze-web` review surface (reuses the contacts-style
propose/review pattern; no new UI paradigm per Assumptions)

**Performance Goals**: Loop extraction and duplicate/re-implication matching run inline with
existing fact/episode writes; no new latency budget beyond what conversation/email/calendar
processing already tolerates. No new hard real-time constraint (Phase A has no proactive
surfacing — that is Phase B).

**Constraints**: Single-user (no `user_id` scoping); confidence decay cascade fires
synchronously at the evidence-writing code path (per Clarification), not via a periodic sweep;
stale-suspicion expiry (~14 days) is the one Phase A behaviour that *does* run as a scheduled
`ze-proactive` job, since it has no natural synchronous trigger.

**Scale/Scope**: Single user's lifetime stream of loops — hundreds to low thousands of rows,
not a scale concern. Four inflows (conversation, email, calendar, ingestion) at Phase A.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Spec-First Development | Spec at `specs/phases/109-open-loop-substrate/spec.md`, clarified, status to be flipped to `Planned`/`In Progress` in the implementing commit | PASS |
| II. Single-User Model | No `user_id` column anywhere in the new schema; loops belong to the one user implicitly | PASS |
| III. Layered Package Architecture | `ze-worldstate` is a new **core** package (not a `ZePlugin`) — it is the concrete form of the world-state's fourth face, part of the spine per `ze-doctrine.md`, exactly as `ze-automation` (goals/workflows) is core infra wired directly into `ze-api` rather than a domain plugin. It depends only on `ze-agents`, `ze-proactive`, `ze-memory`, `ze-data`, `ze-components` — never `ze-core` (engine-internal), matching `ze-automation`'s dependency shape. | PASS |
| IV. Typed, Explicit Python | Dataclasses in `ze_worldstate/types.py` (never `models.py`); Pydantic only in `ze_api/api/schemas.py` for the REST layer; typed `ZeError` subclasses for loop-specific errors; async I/O throughout; constructor injection | PASS |
| V. Test Discipline | Tests in `core/ze-worldstate/tests/`; mock asyncpg with `AsyncMock`; no real embedder/LLM calls in unit tests (embedder injected, mockable) | PASS (planned) |
| VI. Explicit Persistence | New hand-written raw-SQL Alembic chain, prefix `zw`, owned by `ze-worldstate`; `ze-api`'s meta-runner (`migrate.py`) discovers it the same way it discovers `ze-automation`'s `_ZE_AUTOMATION_VERSIONS` | PASS |
| VII. One LLM Gateway, Local Embeddings | Extraction's relevance gate and any LLM-assisted title generation go through the injected `LLMClient`; entity/title similarity reuses the existing injected embedder — no new provider dependency | PASS |

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/phases/109-open-loop-substrate/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── loops-api.md
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
core/ze-worldstate/                       # NEW package — mirrors ze-automation's shape
├── pyproject.toml                        # deps: ze-agents, ze-logging, ze-proactive,
│                                          #       ze-memory, ze-data, ze-components, asyncpg
├── ze_worldstate/
│   ├── __init__.py
│   ├── types.py                          # OpenLoop, LoopState, LoopClaimKind, LoopProvenance
│   ├── errors.py                         # ZeError subclasses (LoopNotFoundError, ...)
│   ├── store.py                          # LoopStore Protocol + PostgresLoopStore
│   ├── matching.py                       # entity-overlap + embedding-similarity dedup (FR-010/011)
│   ├── decay.py                          # confidence decay cascade (FR-004), sync, called at
│   │                                     #   the evidence-writing code path
│   ├── extraction.py                     # conservative relevance-gated loop extraction (FR-008/009)
│   ├── review.py                         # propose→review/confirm/dismiss flow (FR-007),
│   │                                     #   mirrors ze_personal/contacts propose→review shape
│   ├── rest.py                           # plain-dict service functions consumed by ze-api routes
│   │                                     #   (mirrors ze_automation/rest.py)
│   ├── bootstrap.py                      # build_worldstate_stack(shared, settings) — mirrors
│   │                                     #   ze_automation.bootstrap.build_automation_stack
│   ├── jobs/
│   │   └── stale_suspicion.py            # ze-proactive job: expire suspected loops (~14d)
│   └── migrations/
│       ├── env.py
│       └── versions/
│           └── zw001_open_loops.py       # open_loops table (new zw chain)
└── tests/
    ├── test_store.py
    ├── test_matching.py
    ├── test_decay.py
    ├── test_extraction.py
    ├── test_review.py
    └── jobs/
        └── test_stale_suspicion.py

apps/ze-api/ze_api/
├── migrate.py                            # add _ZE_WORLDSTATE_VERSIONS, same pattern as
│                                         #   _ZE_AUTOMATION_VERSIONS
├── container.py                          # wire build_worldstate_stack(shared, settings),
│                                         #   same call shape as build_automation_stack
├── compose.py                            # register stale_suspicion job on the proactive scheduler
└── api/
    ├── schemas.py                        # LoopListItem, LoopDetail, LoopTransitionResponse (Pydantic)
    └── routes/
        └── loops.py                      # GET /api/v0/loops, GET /api/v0/loops/{id},
                                          #   POST /api/v0/loops/{id}/confirm|close|drop

apps/ze-web/src/
├── entities/loop/
│   ├── api/useLoopsQuery.ts
│   ├── api/useLoopTransitionMutation.ts
│   └── index.ts
└── widgets/loop-review/                  # minimal list + confirm/close/drop surface (FR-014/015),
                                          #   same shape as the existing contacts review screen
    └── LoopReviewList.tsx
```

**Structure Decision**: `ze-worldstate` is a new **core** package following the `ze-automation`
precedent exactly (constructor-injected `PostgresLoopStore`, a `bootstrap.py` stack builder, a
`rest.py` of plain-dict functions, its own Alembic chain, its own `ze-proactive` job) rather than
a `ZePlugin`. This is deliberate: the open loop is the concrete form of the *spine's* fourth
face (per `ze-doctrine.md`), not a domain extension — the same reasoning that keeps
`ze-automation` (goals/workflows) out of the plugin layer. `ze-api` is the only place that wires
`ze-worldstate` to concrete inflows (conversation turn processing, `ze-messenger`'s email
ingestion, `ze-calendar`'s sync, the ingestion pipeline) by calling `ze_worldstate.extraction`
directly from those existing write paths — this is FR-017's proto-contribution: a direct call,
not a new seam.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified

No violations. Table intentionally omitted.
