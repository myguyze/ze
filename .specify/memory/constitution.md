# Ze Constitution

Ze is a single-user personal AI assistant: a Python/FastAPI backend with a LangGraph
orchestration layer routing messages to specialised agents, a React web client over
WebSocket, and ntfy push notifications. This constitution states the non-negotiable
principles every feature must respect. The detailed conventions live in `CLAUDE.md`
and the ADRs in `specs/arch/` — when in doubt, those documents elaborate; this one
governs.

## Core Principles

### I. Spec-First Development
No feature is implemented without a spec. Feature specs live in
`specs/phases/NNN-<name>/` (spec-kit layout: `spec.md`, `plan.md`, `research.md`,
`tasks.md`, `contracts/`, …). Core infrastructure specs live in `specs/core/`;
cross-cutting decisions are ADRs in `specs/arch/`. The status field in a spec header
is authoritative and must be updated in the same commit as the implementation.

### II. Single-User Model
Ze serves exactly one person. No `user_id` columns, no multi-tenancy, no roles.
Auth is a single API key. Any design that introduces per-user scoping violates
`specs/arch/single-user-model.md` and must be rejected at plan time.

### III. Layered Package Architecture
The dependency direction is absolute: `core/` packages have no domain knowledge,
`plugins/` extend via `ZePlugin` and import only from `ze_sdk.*` (never `ze_core.*`,
never `ze_plugin.*` directly), `integrations/` wrap external services with no Ze
domain knowledge, and `apps/` are the only composition roots. New capabilities that
belong to a domain go in a plugin, not the engine.

### IV. Typed, Explicit Python
Dataclasses for domain types (`types.py`, never `models.py`); Pydantic only in
`ze_api/api/schemas.py`. Errors are typed `ZeError` subclasses — never bare
`Exception` or `ValueError` in domain code. All I/O is async. Dependencies arrive by
constructor injection; FastAPI `Depends()` only inside `ze_api/api/`. Logging via
`get_logger(__name__)` only.

### V. Test Discipline (NON-NEGOTIABLE)
Every feature ships with tests in `<package>/tests/` (Python) or `src/**/*.test.ts(x)`
(ze-web). Unit tests touch no real database (mock asyncpg with `AsyncMock`) and no
real LLM (mock `client.complete`/`client.stream`). Slow embedding tests are marked
`@pytest.mark.slow`. A task is not done until `make test-<package>` and `make lint`
pass.

### VI. Explicit Persistence
Schema changes are hand-written raw-SQL Alembic migrations in the package that owns
the tables, on that package's revision chain (`zc`, `zm`, `zcal`, …). No ORM. ze-api
runs all chains but owns no tables. Cross-package ordering uses `depends_on`.

### VII. One LLM Gateway, Local Embeddings
All LLM calls go through OpenRouter via the injected `LLMClient`; embeddings are the
local `paraphrase-multilingual-MiniLM-L12-v2` singleton. No direct provider SDKs, no
per-feature API keys.

## Additional Constraints

- Frontend follows Feature-Sliced Design: `pages → widgets → features → entities →
  shared`, imports only downward. Query hooks live in `entities/<name>/api/`.
- Configuration: secrets in `.env`, structure in `config/*.yaml`; agent config lives
  on `@agent` class attributes, not YAML.
- Comments default to none — only when the *why* is non-obvious.
- No module-level mutable globals outside the sanctioned `lru_cache` singletons.

## Development Workflow

Features flow through the spec-kit pipeline: `/speckit-specify` (spec) →
`/speckit-clarify` (optional de-risking) → `/speckit-plan` (plan + research +
contracts) → `/speckit-tasks` → `/speckit-analyze` (optional consistency check) →
`/speckit-implement`. Feature numbering continues Ze's phase sequence (three-digit,
next free number). Definition of Done for any phase includes: spec status updated,
tests green, lint clean, and `specs/README.md` index row updated.

## Governance

This constitution supersedes ad-hoc practice. Amendments are made via an ADR in
`specs/arch/` plus a version bump here, in the same commit. Plans produced by
`/speckit-plan` must include a Constitution Check gate; violations must be either
removed or justified in the plan's Complexity Tracking section. Runtime development
guidance for agents lives in `CLAUDE.md`.

**Version**: 1.0.0 | **Ratified**: 2026-07-09 | **Last Amended**: 2026-07-09
