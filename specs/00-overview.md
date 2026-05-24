# Ze — System Overview

## Purpose

Ze is a personal AI assistant that routes user prompts to specialised sub-agents,
executes tasks with configurable permission levels, and maintains persistent memory
of user facts and interaction history. It is strictly single-user, self-hosted on
Fly.io, and accessed via Telegram.

## Core Design Principles

- **Minimise LLM calls.** Local sentence-transformer embeddings handle routing in
  the happy path. No LLM is invoked until an agent actually needs to act.
- **Configurability over automation.** Every agent action has an explicit permission
  mode. Ze does not take write-risk actions autonomously unless the user has opted in
  via `capabilities.yaml`.
- **Memory as editorial problem.** Agents propose facts and episodes; the user
  approves what is stored. Ze never silently writes to long-term memory.
- **Modular agents.** Each agent is isolated — its own system prompt, tool registry,
  model config, and intent map. Agents cannot call each other directly.
- **Spec-first development.** No module is implemented without a reviewed spec.
  Open Questions in a spec must be resolved or explicitly deferred before
  implementation begins.
- **Dependency injection throughout.** Every module accepts its dependencies as
  constructor arguments. FastAPI `Depends()` handles wiring at the API layer.
  Nothing reads from globals or `os.environ` directly except `ze/settings.py`.

## System Flow

```
User message (Telegram Bot API)
        │
        ▼
  [embed_route]  ──── cosine similarity ──── local sentence-transformer (ze/embeddings.py)
        │
        ├─ confident + single agent ──────────────────────────────────────┐
        │                                                                  │
        └─ ambiguous / compound ──── [decompose] (Haiku via OpenRouter) ──┤
                                                                           │
                                                              [fetch_context]
                                                           (pgvector search, ze/memory)
                                                                           │
                                                           [capability_check]
                                                            (ze/capability/gate.py)
                                                                           │
                                              ┌────────────────────────────┼──────────────────────┐
                                              │                            │                      │
                                           EXECUTE                      DRAFT            AWAIT_CONFIRMATION
                                              │                            │                      │
                                       [execute_tool]             [draft_response]    [await_confirmation]
                                              │                            │             (graph paused,
                                              │                            │           AsyncPostgresSaver)
                                              └────────────────────────────┴──────────────────────┘
                                                                           │
                                                               [synthesize] (compound tasks only)
                                                                           │
                                                               [write_memory] (always runs)
                                                                           │
                                                  Response sent via Telegram Bot API
                                             (typing action while running → full message)
```

## Agent Roster

| Agent       | Primary Capability                                    | Default Risk |
|-------------|-------------------------------------------------------|--------------|
| `calendar`  | Read, create, update, delete Google Calendar events   | Medium       |
| `email`     | Read, draft, send Gmail messages                      | High         |
| `research`  | Web search (Tavily), summarisation, fact extraction   | Low          |
| `workflow`  | File operations, API triggers, automations            | Variable     |
| `companion` | Reasoning, thinking partner — no external tool calls  | None         |

## Implementation Phases

| Phase | Scope                                                                        | Status  |
|-------|------------------------------------------------------------------------------|---------|
| 1     | `research` + `companion` only. Full stack vertical slice.                    | ✅ Done |
| 2     | Memory (pgvector), capability gate, confirmation + draft UI.                 | ✅ Done |
| 3     | `calendar` + `email`, Google OAuth2, compound task decomposition.            | ✅ Done |
| 4     | `workflow`, memory digest, routing log UI, capability config UI.             | ✅ Done |
| 5     | Memory consolidation — dedup facts, expire stale, summarise episodes.        | ✅ Done |
| 6     | User profile — synthesise facts + episodes into a structured portrait.       | ✅ Done |
| 7     | Proactive Ze — morning briefing, workflow failure alerts, calendar reminders. | ✅ Done |
| 8     | Insight engine — weekly synthesis of facts + episodes into actionable insights. | ✅ Done |
| 9     | Cost telemetry — per-flow/agent token tracking, automatic cost reconciliation. | ✅ Done |
| 10    | Multimodal input — voice transcription + image/vision support.               | ✅ Done |
| 11    | Persona profiles + dials — named profiles, TARS-style dials, `/persona` cmd. | ✅ Done |
| 12    | Contacts — person tracking, extraction from email/calendar/conversation, confirmation flow. | ✅ Done |
| 13    | Reminders agent — NL time parsing, APScheduler firing, startup replay.       | ✅ Done |
| 14    | Progress messages — per-agent Telegram status messages, locale keys.         | ✅ Done |
| 15    | Telegram commands — `/costs`, `/memory`, `/contacts` introspection.          | ✅ Done |
| 16    | Agentic tool loop — LLM-driven ReAct loop in `BaseAgent`.                    | ✅ Done |
| 17    | Prospecting agent — autonomous target research, browser extraction, outreach drafting. | 🔲 Pending |

## Module Map

| Spec                          | Module                        | New Phase |
|-------------------------------|-------------------------------|-----------|
| `00-overview.md`              | This document                 | —         |
| `01-routing.md`               | Embedding router              | 1         |
| `02-capability-gate.md`       | Capability gate               | 2         |
| `03-memory.md`                | Memory system                 | 2         |
| `04-agents.md`                | Sub-agent defs                | 1–4       |
| `05-orchestration.md`         | LangGraph graph               | 1         |
| `06-openrouter-client.md`     | OpenRouter client             | 1         |
| `07-api.md`                   | FastAPI + Telegram            | 1         |
| `08-telegram.md`              | Telegram Bot                  | 1         |
| `09-agent-tool-api.md`        | Agent tool protocol           | 4         |
| `10-phase3-google.md`         | Calendar + Gmail agents       | 3         |
| `11-persona.md`               | Companion persona             | 1–2       |
| `12-workflow.md`              | Workflow agent + scheduler    | 4         |
| `13-phase5-memory.md`         | Memory consolidation          | 5         |
| `14-user-profile.md`          | User profile synthesis        | 6         |
| `19-multimodal-input.md`      | Voice + image input           | 10        |
| `25-persona-profiles.md`      | Persona profiles + dials      | 11        |

## Cross-Cutting Modules

These live at the root of `ze/` and are imported by all other modules.

| Module            | Purpose                                                           |
|-------------------|-------------------------------------------------------------------|
| `settings.py`     | Pydantic `BaseSettings`. Single source for all config and secrets.|
| `errors.py`       | Base exception hierarchy. All modules raise from here.            |
| `logging.py`      | structlog JSON logger. Session-id and agent bound at request time.|
| `embeddings.py`   | Shared `SentenceTransformer` singleton. Loaded once at startup.   |
| `db.py`           | asyncpg pool factory. Lifespan-managed. Injected via `Depends()`. |

## Configuration Files

| File                           | Purpose                                         |
|--------------------------------|-------------------------------------------------|
| `.env`                         | Secrets — API keys, DB URL, timeouts.           |
| `config/capabilities.yaml`     | Permission mode per `agent.intent`.             |
| `config/models.yaml`           | Model assignments, routing thresholds, timeouts.|
| `config/agents/<name>.yaml`    | Per-agent description, tools, intent map.       |

## Resolved Constraints

- **Single user.** No multi-tenant memory, no user isolation, no session auth beyond
  a static API key (`ZE_API_KEY` in `.env`).
- **All LLM calls via OpenRouter.** No direct Anthropic/OpenAI calls.
- **Google API auth.** Out of scope for Phase 1. Phase 3 uses local OAuth2 token
  store (stored in Fly.io secrets after first auth). Service accounts are not
  suitable for personal calendar/email access.
- **Mobile interface.** Delivered natively through Telegram. No separate mobile app required.

## Open Questions

- [x] Phase 3: OAuth2 strategy resolved — Google OAuth2 (Calendar + Gmail).
  Refresh token stored as `GOOGLE_REFRESH_TOKEN` Fly.io secret. Access token
  exchanged at startup and on every 401. One OAuth2 flow run once locally via
  a temporary CLI script; refresh token never touches the DB.
- [x] Phase 4: workflow agent scoped to APScheduler-based multi-step plan execution with Postgres persistence. File operations and external API triggers are capabilities exposed via agent tools, not a separate integration layer.
