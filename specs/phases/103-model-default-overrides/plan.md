# Implementation Plan: Model Default with Overrides

**Branch**: `103-model-default-overrides` | **Date**: 2026-07-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/phases/103-model-default-overrides/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Every LLM call site in Ze currently resolves its model independently: agents read a
hardcoded `model = "..."` class attribute, and non-agent steps (synthesis, session
titling, workflow verification, router decomposition fallback, insights, reminder
assessment) each read their own `config["models"][key]` lookup with a hardcoded
Python fallback constant. There is no single override-with-fallback chain, so trying
a new model everywhere means editing 7+ files. This feature introduces one shared
resolver (`resolve_model(key, declared, config)`) used by every general
chat-completion call site, backed by two new config.yaml keys — `models.default`
(required global fallback) and `models.overrides` (optional per-key pins) — with
resolution order override → declared → default. Capability-specific model keys
(`models.embedding`, `models.whisper`, `models.vision_caption`) are left exactly as
they are today: explicit, pinned, untouched by the resolver. As part of this change,
`models.default` is set to `tencent/hy3:free` to trial it through 2026-07-21.

Research also surfaced a latent bug worth fixing in the same change: several call
sites (`synthesize`, `_resolve_verify_model`, the insights job, the reminders
interval assessor) read `config["models"][key]`, but config.yaml currently defines
those same keys under `routing:`, not `models:` — so today, editing
`routing.synthesis`, `routing.workflow_verify`, `routing.insights`, or
`routing.reminders` in config.yaml has **no effect at all**; those calls always fall
through to their hardcoded Python constant. Consolidating everything onto the new
`models.overrides` map (which every call site now actually reads) fixes this as a
side effect.

## Technical Context

**Language/Version**: Python 3.12 (backend packages), TypeScript/React (ze-web — untouched by this feature)

**Primary Dependencies**: FastAPI, LangGraph, `ze-agents`/`ze-core`/`ze-automation` internal packages, PyYAML (existing `Settings.config` YAML loader), OpenRouter via `LLMClient`

**Storage**: N/A — this is a configuration-resolution change; no new persisted state, no schema changes, no migrations

**Testing**: pytest (`make test-core`, `make test-personal`, `make test-calendar`, `make test-api` — packages touched by this change), `asyncio_mode = "auto"`, no real DB/LLM in unit tests

**Target Platform**: Existing Ze backend (Linux/macOS dev, containerized deploy) — no new platform surface

**Project Type**: Backend library/config change inside the existing Ze monorepo (`core/`, `plugins/`, `apps/ze-api/`) — no new package

**Performance Goals**: N/A — resolution is a plain dict lookup on an already-in-memory config dict; no measurable latency impact

**Constraints**: Must preserve today's config hot-reload behavior (config.yaml is re-read from disk on every `Settings.config` access — see research.md — no restart, no signal handling required); must not change behavior for capability-specific models (whisper/vision_caption/embedding)

**Scale/Scope**: 8 call sites across `ze-core`, `ze-personal`, `ze-calendar`, `ze-api` migrated to the shared resolver; one new module (`ze_agents.model_resolution`); one config.yaml restructure; no new agents, no new API surface

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-First Development** — PASS. Spec exists at `specs/phases/103-model-default-overrides/spec.md`, status will be updated in the implementation commit.
- **II. Single-User Model** — PASS. No user-scoping introduced; config is process-global, matching the single-user model.
- **III. Layered Package Architecture** — PASS. The new resolver lives in `ze-agents` (already the shared home for `defaults.py`/`settings.py`/`errors.py`, already directly imported by plugins today — e.g. `ze_personal/graph/workflow.py` imports `ze_agents.defaults` directly). `ze-core` continues to depend on `ze-agents`; no plugin gains a new `ze-core` or `ze-plugin` dependency.
- **IV. Typed, Explicit Python** — PASS. Resolution failures raise the existing `AgentConfigError` (subclass of `ZeError`/`AgentError`), not a bare exception. No Pydantic introduced outside `ze_api/api/schemas.py`.
- **V. Test Discipline** — PASS. New unit tests for the resolver (pure function, no DB/LLM) plus updated tests at each of the 8 call sites, run via existing `make test-<package>` targets.
- **VI. Explicit Persistence** — PASS. No schema change, no migration.
- **VII. One LLM Gateway, Local Embeddings** — PASS. All resolved models are still dispatched through the existing `LLMClient`/OpenRouter path; `models.embedding` (the one non-OpenRouter, local-embedding key) is explicitly excluded from the resolver and untouched.
- **Additional Constraint — "agent config lives on `@agent` class attributes, not YAML"** — TENSION, justified below in Complexity Tracking. This constraint targets agent *identity* config (description, intents, tools) staying in code for discoverability. Model *selection* is already partially YAML-driven today (the existing, currently-broken `routing.synthesis`/`routing.workflow_verify`/etc. keys prove the precedent exists) — this feature formalizes and fixes that existing pattern rather than introducing a new one, and an agent's class attribute remains the meaningful "declared default" in the resolution chain, not something YAML silently replaces by default.

## Project Structure

### Documentation (this feature)

```text
specs/phases/103-model-default-overrides/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

No `contracts/` directory: this feature has no external interface (no new REST/WS
endpoint, no new CLI). It changes internal model-resolution behavior and a
configuration file schema only. The config.yaml schema itself is documented in
`data-model.md` in lieu of a formal contract.

### Source Code (repository root)

```text
core/ze-agents/ze_agents/
├── model_resolution.py          # NEW — resolve_model(key, declared, config); KNOWN_STEP_KEYS registry;
│                                 #        validate_model_config(config, agent_names) for startup fail-fast
└── tests/test_model_resolution.py   # NEW — resolver unit tests

core/ze-core/ze_core/
├── routing/router.py             # EDIT — _resolve_model() calls resolve_model() instead of reading
│                                 #        agent_cls.model directly
├── orchestration/nodes/memory.py # EDIT — synthesize() calls resolve_model("synthesis", MODEL_SYNTHESIS, cfg)
├── container.py                  # EDIT — RouterConfig.fallback_model wiring calls resolve_model();
│                                 #        calls validate_model_config() once at startup (fail-fast)
└── tests/                        # EDIT — update existing router/memory/container tests for new resolution path

plugins/ze-personal/ze_personal/
├── graph/workflow.py             # EDIT — _resolve_verify_model() calls resolve_model()
├── jobs/insights.py               # EDIT — model lookup calls resolve_model()
└── tests/                        # EDIT — update existing tests

plugins/ze-calendar/ze_calendar/
├── reminders/calendar.py         # EDIT — _assess_intervals() model lookup calls resolve_model()
└── tests/                        # EDIT — update existing tests

apps/ze-api/
├── ze_api/api/websocket/session_titles.py   # EDIT — calls resolve_model("session_title", ..., cfg)
├── config/config.yaml            # EDIT — restructure `models:` section (see data-model.md);
│                                 #        remove dead routing.synthesis/profile/reminders/insights/
│                                 #        whisper/vision_caption/workflow_verify keys; set
│                                 #        models.default: tencent/hy3:free
└── tests/                        # EDIT — startup validation test (missing default / unknown override key)

docs/configuration.md             # EDIT — document models.default / models.overrides resolution order
```

**Structure Decision**: No new package. This is a cross-cutting change to existing
call sites in `ze-core` (engine), two plugins (`ze-personal`, `ze-calendar`) that
already import `ze_agents` directly, and `ze-api` (config file + one route). The
shared resolver lives in `ze-agents` because it is the lowest layer already common
to every touched package (`ze-core` → `ze-agents`; both plugins already depend on
`ze-agents` transitively via `ze-sdk` and also import it directly today), avoiding
any new cross-layer dependency.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| YAML can now override an agent's declared `model` class attribute (tension with "agent config lives on class attributes, not YAML") | The entire point of the feature (per spec User Stories 1–2) is to let a maintainer change models fleet-wide or per-agent via config, with zero code edits and zero restart — that is impossible if model selection stays code-only | Keeping model selection purely in class attributes was considered and rejected: it's the exact status quo that motivated this spec (a model trial currently requires hand-editing 7+ files). The blast radius is intentionally narrow — only the model string, not `description`/`intents`/`tools`, moves under config influence, and the class attribute is preserved as the middle tier of the fallback chain (not deleted), so agent identity/behavior config stays exactly where the constitution requires it |
