# Ze Specs

Design and implementation specs for the Ze personal AI assistant.

## Structure

```
specs/
├── phases/            ← feature specs, one spec-kit directory per feature
│   └── NNN-<name>/    ←   spec.md (+ plan.md, research.md, tasks.md, contracts/, …)
├── core/              ← ze-core infrastructure layer specs
└── arch/              ← architecture decision records
```

Feature specs follow the [GitHub spec-kit](https://github.com/github/spec-kit)
workflow (see [arch/spec-kit-adoption.md](arch/spec-kit-adoption.md)). Scaffolding
lives in `.specify/`; the pipeline runs as Claude Code skills.

## Writing a new spec

| What you are writing | How | Destination |
|----------------------|-----|-------------|
| New feature or phase | `/speckit-specify <description>` | `phases/NNN-<name>/spec.md` |
| New ze-core module | follow an existing `core/ze-*.md` spec | `core/<name>.md` |
| Cross-cutting design decision | follow an existing ADR in `arch/` | `arch/<name>.md` |

**Feature pipeline** (spec-kit): `/speckit-specify` → `/speckit-clarify` (optional,
de-risk ambiguity) → `/speckit-plan` (plan + research + data-model + contracts) →
`/speckit-tasks` → `/speckit-analyze` (optional consistency check) →
`/speckit-implement`. Numbering continues the phase sequence automatically
(three-digit, next free number). The project constitution that plans are checked
against lives in `.specify/memory/constitution.md`.

**Required sections by type:**
- Feature: whatever `.specify/templates/spec-template.md` generates — user scenarios, requirements, success criteria
- ADR: Context and Problem Statement, Considered Options, Decision Outcome
- Core: Purpose, Responsibilities, Out of Scope

**Status is authoritative in the spec header.** The index tables below are
navigation aids — update both, but when they diverge the spec header wins.

All Open Questions / `[NEEDS CLARIFICATION]` markers must be resolved (or
explicitly deferred with a target date) before setting status → Done.

## Phase specs (`phases/`)

Legend: ✅ Done · 🔄 In Progress · 🔲 Pending · ⏸ Deferred · ⚠️ Deprecated

| # | Spec | Status |
|---|------|--------|
| 00 | [Overview](phases/000-overview/spec.md) | ✅ Current |
| 01 | [Routing](phases/001-routing/spec.md) | ✅ Done |
| 02 | [Capability Gate](phases/002-capability-gate/spec.md) | ⚠️ Deprecated → `core/03` |
| 03 | [Memory](phases/003-memory/spec.md) | ✅ Done |
| 04 | [Agents](phases/004-agents/spec.md) | ⚠️ Deprecated → `core/01` |
| 05 | [Orchestration](phases/005-orchestration/spec.md) | ✅ Done |
| 06 | [OpenRouter Client](phases/006-openrouter-client/spec.md) | ✅ Done |
| 07 | [API](phases/007-api/spec.md) | ✅ Done |
| 08 | [Telegram Bot](phases/008-telegram/spec.md) | ✅ Done |
| 09 | [Agent & Tool API](phases/009-agent-tool-api/spec.md) | ✅ Done |
| 10 | [Google Calendar + Gmail](phases/010-phase3-google/spec.md) | ✅ Done |
| 11 | [Persona](phases/011-persona/spec.md) | ✅ Done |
| 12 | [Workflow](phases/012-workflow/spec.md) | ✅ Done |
| 13 | [Memory Consolidation](phases/013-phase5-memory/spec.md) | ✅ Done |
| 14 | [User Profile](phases/014-user-profile/spec.md) | ✅ Done |
| 15 | [Proactive Ze](phases/015-proactive-ze/spec.md) | ✅ Done |
| 16 | [Insight Generation](phases/016-insight-generation/spec.md) | ✅ Done |
| 17 | [Cost Telemetry](phases/017-cost-telemetry/spec.md) | ✅ Done |
| 18 | [Cost-Aware Routing](phases/018-cost-aware-routing/spec.md) | ✅ Done |
| 19 | [Multimodal Input](phases/019-multimodal-input/spec.md) | ✅ Done |
| 20 | [Contacts](phases/020-contacts/spec.md) | ✅ Done |
| 21 | [Telegram Commands](phases/021-telegram-commands/spec.md) | ✅ Done |
| 22 | [Reminders Agent](phases/022-reminders-agent/spec.md) | ✅ Done |
| 23 | [Eval](phases/023-eval/spec.md) | ✅ Done |
| 24 | [Agentic Tool Loop](phases/024-agentic-tool-loop/spec.md) | ✅ Done |
| 25 | [Persona Profiles + Dials](phases/025-persona-profiles/spec.md) | ✅ Done |
| 26 | [Prospecting Agent](phases/026-prospecting-agent/spec.md) | ✅ Done |
| 27 | [Channels](phases/027-channels/spec.md) | ✅ Done |
| 28 | [Goal Engine](phases/028-goal-engine/spec.md) | ✅ Done |
| 29 | [Progress Messages](phases/029-progress-messages/spec.md) | ✅ Done |
| 30 | [Agent Harness](phases/030-agent-harness/spec.md) | ✅ Done |
| 31 | [Goal Engine v2](phases/031-goal-engine-v2/spec.md) | ✅ Done |
| 32 | [Goal Collaboration](phases/032-goal-collaboration/spec.md) | ✅ Done |
| 33 | [Proactive Goal Suggestions](phases/033-goal-suggestions/spec.md) | ✅ Done |
| 34 | [Stuck Goal Detection](phases/034-stuck-goal-detection/spec.md) | ✅ Done |
| 35 | [Cross-Goal Output Reuse](phases/035-cross-goal-output-reuse/spec.md) | ✅ Done |
| 36 | [Cross-Goal Learning Promotion](phases/036-cross-goal-learning-promotion/spec.md) | ✅ Done |
| 37 | [News Package](phases/037-news-package/spec.md) | ✅ Done |
| 38 | [News Personalization](phases/038-news-personalization/spec.md) | ✅ Done |
| 39 | [News Credibility](phases/039-news-credibility/spec.md) | ✅ Done |
| 40 | [Notifications](phases/040-notifications/spec.md) | ✅ Done |
| 41 | [Component Descriptors](phases/041-component-descriptors/spec.md) | ✅ Done |
| 42 | [Native UI Foundation](phases/042-native-ui-foundation/spec.md) | ✅ Done |
| 43 | [React Web App](phases/043-react-web-app/spec.md) | ✅ Done |
| 44 | [Calendar Package Split](phases/044-package-split-google-calendar-api/spec.md) | ✅ Done |
| 46 | [Accountability Layer](phases/046-accountability-layer/spec.md) | ✅ Done |
| 47 | [Plugin Framework](phases/047-plugin-framework/spec.md) | ✅ Done (tool namespacing deferred) |
| 48 | [Ze Core Split](phases/048-core-split/spec.md) | ✅ Done |
| 49 | [Ze SDK](phases/049-ze-sdk/spec.md) | ✅ Done |
| 50 | [News Preference Model](phases/050-news-preferences/spec.md) | ✅ Done |
| 51 | [Onboarding Platform](phases/051-onboarding/spec.md) | ✅ Done |
| 52 | [Session-Grouped Episode Consolidation](phases/052-session-grouped-consolidation/spec.md) | ✅ Done |
| 53 | [Eval Consolidation](phases/053-eval-consolidation/spec.md) | ✅ Done |
| 54 | [Progress Messages](phases/054-progress-messages/spec.md) | ✅ Done |
| 55 | [Signal Substrate](phases/055-signal-substrate/spec.md) | ✅ Done |
| 56 | [Salience & Relevance Model](phases/056-salience-relevance-model/spec.md) | ✅ Done |
| 57 | [Correlation Engine](phases/057-correlation-engine/spec.md) | ✅ Done |
| 58 | [Inline Conversational Correlation](phases/058-inline-correlation/spec.md) | ✅ Done |
| 59 | [Proactive Correlation Push](phases/059-proactive-correlation-push/spec.md) | ⏸ Deferred (post-v1) |
| 60 | [Cross-Plugin Signal Contract](phases/060-signal-source-contract/spec.md) | ✅ Done |
| 61 | [Convergence & Pressure Points](phases/061-convergence-pressure-points/spec.md) | 🔲 Pending (design-only) |
| 62 | [Data Portability](phases/062-data-portability/spec.md) | ✅ Done |
| 63 | [Integration Framework](phases/063-integration-framework/spec.md) | ✅ Done |
| 64 | [Plugin Package Extraction](phases/064-plugin-package-extraction/spec.md) | ✅ Done |
| 65 | [Eager Session Summaries](phases/065-eager-session-summaries/spec.md) | ✅ Done |
| 66 | [Primitive UI](phases/066-primitive-ui/spec.md) | ✅ Done |
| 67 | [Finance Plugin](phases/067-finance-plugin/spec.md) | ✅ Done |
| 68 | [ze-data Package](phases/068-ze-data/spec.md) | ✅ Done |
| 69 | [ze-ingestion Pipeline](phases/069-ze-ingestion/spec.md) | ✅ Done |
| 70 | [Finance Recurring Detection](phases/070-finance-recurring/spec.md) | ✅ Done |
| 71 | [Cross-Goal Awareness](phases/071-cross-goal-awareness/spec.md) | 🔲 Pending |
| 72 | [API Client Codegen](phases/072-api-client-codegen/spec.md) | ✅ Done |
| 73 | [API Surface](phases/073-api-surface/spec.md) | ✅ Done |
| 74 | [Automation Substrate](phases/074-automation-substrate/spec.md) | ✅ Done |
| 75 | [Server-Driven UI Package](phases/075-server-driven-ui-package/spec.md) | ✅ Done |
| 76 | [ze-api Shell Cleanup](phases/076-ze-api-shell-cleanup/spec.md) | ✅ Done |
| 77 | [ze-logging Package](phases/077-ze-logging/spec.md) | ✅ Done |
| 78 | [Dream Memory](phases/078-dream-memory/spec.md) | 🔄 In Progress |
| 79 | [NLI Cross-Encoder Integration](phases/079-nli-model/spec.md) | ✅ Done |
| 80 | [NLI Client + Plugin Access](phases/080-nli-client/spec.md) | ✅ Done |
| 81 | [Plugin NLI Adoption](phases/081-plugin-nli-adoption/spec.md) | ✅ Done |
| 82 | [ze-web FSD Restructure](phases/082-ze-web-fsd/spec.md) | ✅ Done |
| 83 | [ze-communication + ze-messenger](phases/083-ze-communication/spec.md) | ✅ Done |
| 84 | [Webhook Infrastructure](phases/084-webhooks/spec.md) | 🔲 Pending |
| 85 | [Ze Messaging Hub](phases/085-messaging-hub/spec.md) | 🔲 Pending |
| 87 | [Plugin UI Platform](phases/087-plugin-ui/spec.md) | ✅ Done |
| 88 | [Memory Feed](phases/088-memory-feed/spec.md) | 🔲 Pending |
| 89 | [Message Trace](phases/089-message-trace/spec.md) | 🔲 Pending |
| 90 | [Ze's Mind Split-Pane](phases/090-ze-mind-split-pane/spec.md) | 🔲 Pending |
| 91 | [Goal Dashboard v2](phases/091-goal-dashboard-v2/spec.md) | 🔲 Pending |
| 92 | [Agent Activity Heatmap](phases/092-agent-activity-heatmap/spec.md) | ✅ Done |
| 93 | [Temporal Memory Timeline](phases/093-temporal-memory-timeline/spec.md) | 🔲 Pending |
| 94 | [Memory Graph View](phases/094-memory-graph-view/spec.md) | 🔲 Pending |
| 95 | [Unified Streaming Architecture](phases/095-live-trace-streaming/spec.md) | 🔲 Pending |
| 96 | [Dev Data Seeder](phases/096-dev-data-seeder/spec.md) | 🔲 Pending |
| 97 | [Embedding Model Upgrade (MiniLM → E5)](phases/097-embedding-model-upgrade/spec.md) | 🔲 Pending |
| 98 | [Workflow Run Chat](phases/098-workflow-run-chat/spec.md) | 🔲 Pending |
| 99 | [Multi-Conversation Support](phases/099-multi-conversation/spec.md) | 🔲 Pending |
| 101 | [Session Search & Titles](phases/101-session-search/spec.md) | ✅ Done |
| 102 | [Workflow Conditional Branching](phases/102-workflow-branching/spec.md) | ✅ Done |
| 103 | [Model Default with Overrides](phases/103-model-default-overrides/spec.md) | ✅ Done |

## Ze Core specs (`core/`)

One spec per package in `core/`. The old numbered specs (01–09) are stale — they
describe the pre-split monolithic `ze-core` and are kept only as historical reference.

### Current package specs

| Package | Spec | What it owns |
|---------|------|-------------|
| `ze-core` | [ze-core.md](core/ze-core.md) | Orchestration engine — routing, graph, capability, telemetry, container |
| `ze-agents` | [ze-agents.md](core/ze-agents.md) | Developer API — `@agent`, `BaseAgent`, `@tool`, `LLMClient`, error hierarchy |
| `ze-plugin` | [ze-plugin.md](core/ze-plugin.md) | Plugin extension framework — `ZePlugin` ABC, entry points, lifecycle hooks |
| `ze-sdk` | [ze-sdk.md](core/ze-sdk.md) | Plugin entry point — flat re-export of everything plugin authors need |
| `ze-proactive` | [ze-proactive.md](core/ze-proactive.md) | Job scheduling — `ProactiveJob`, `ProactiveScheduler`, push log |
| `ze-memory` | [ze-memory.md](core/ze-memory.md) | Memory stack — facts, episodes, graph, consolidation, dream |
| `ze-automation` | [ze-automation.md](core/ze-automation.md) | Automation — goals, workflows, accountability, GoalAgent, WorkflowAgent |
| `ze-communication` | [ze-communication.md](core/ze-communication.md) | Channel contract — `Channel` ABC, `InboundChannel`, `ChannelRegistry` |
| Smaller packages | [ze-smaller-packages.md](core/ze-smaller-packages.md) | ze-logging, ze-notifications, ze-browser, ze-data, ze-components, ze-correlation, ze-eval, ze-onboarding, ze-ingestion, ze-seed |

### Legacy specs (stale — pre-split, for historical reference only)

| # | Spec | What it described |
|---|------|------------------|
| 01 | [Agent Decorator & BaseAgent](core/01-agent.md) | `@agent` + `BaseAgent` inside old `ze_core` |
| 02 | [AppInterface](core/02-app-interface.md) | `AppInterface` ABC inside old `ze_core` |
| 03 | [Capability Gate](core/03-capability-gate.md) | `CapabilityGate` inside old `ze_core` |
| 04 | [Routing](core/04-routing.md) | `EmbeddingRouter` inside old `ze_core` |
| 05 | [Orchestration Graph](core/05-orchestration.md) | LangGraph graph inside old `ze_core` |
| 06 | [Memory](core/06-memory.md) | Memory before `ze-memory` extraction |
| 07 | [Container](core/07-container.md) | DI container inside old `ze_core` |
| 08 | [Contacts](core/08-contacts.md) | Contacts primitive before `ze-personal` |
| 09 | [Conversation Persistence](core/09-conversation.md) | Session/message store |

## Architecture decisions (`arch/`)

### Foundational choices

These are the load-bearing decisions that shape the entire codebase. Every contributor
should read them before changing anything structural.

| ADR | Decision |
|-----|----------|
| [Single-User Model](arch/single-user-model.md) | No `user_id` anywhere; auth is a single API key; Ze serves one person |
| [OpenRouter Gateway](arch/openrouter-gateway.md) | All LLM calls through OpenRouter only — single billing, config-driven model swaps |
| [LangGraph Orchestration](arch/langgraph-orchestration.md) | LangGraph + AsyncPostgresSaver — durable graph execution with confirmation-flow pause/resume |
| [Local Embeddings](arch/local-embeddings.md) | `paraphrase-multilingual-MiniLM-L12-v2` in-process — zero cost, multilingual, hot-path safe |
| [Dataclasses over Pydantic](arch/dataclasses-over-pydantic.md) | `@dataclass` in all domain code; Pydantic only in `ze_api/api/schemas.py` |
| [Alembic Raw SQL](arch/alembic-raw-sql.md) | Hand-written SQL migrations; per-package chains; no ORM |
| [asyncpg + psycopg2 split](arch/asyncpg-psycopg2-split.md) | asyncpg for runtime, psycopg2 for Alembic CLI — asyncpg has no sync mode |
| [ntfy Push Notifications](arch/ntfy-push-notifications.md) | Self-hostable REST-based push; no vendor approval; deep-link support |

### Structural decisions

Made when a significant restructuring forced the question.

| ADR | Decision |
|-----|----------|
| [Package Reorg](arch/package-reorg.md) | Monorepo split: ze-core / ze-personal / ze / ze-browser |
| [Plugin Agents](arch/plugin-agents.md) | ZePlugin ABC, domain agent migration to ze-personal |
| [Monorepo Layout](arch/monorepo-layout.md) | Dissolve `packages/`; promote `core/`, `plugins/`, `apps/` to repo root |
| [Memory Package Extraction](arch/memory-package-split.md) | Hard-cut memory into `ze_memory` with module-specific retrieval, explicit task state, and no shim |
| [Memory Graph Augmentation](arch/memory-graph-augmentation.md) | Add bounded, provenance-first relationships and traversal inside `ze_memory` |
| [Dream Memory](arch/dream-memory.md) | Offline wake/sleep/dream/morning consolidation loop; staging buffer + critic-gated promotion |
| [Correlation Engine](arch/correlation-engine.md) | Bounded relevance-gated correlation over a shared signal/graph substrate; not a world model |
| [Communication Hub](arch/communication-hub.md) | Channel identity contract, thread ownership, memory contribution policy, signal filtering, extensibility |
| [Plugin UI](arch/plugin-ui.md) | Three-tier plugin UI model (SDUI, manifest + generic shell, optional frontend modules) |
| [spec-kit Adoption](arch/spec-kit-adoption.md) | Feature specs use GitHub spec-kit (`specs/phases/NNN-<name>/` dirs, `.specify/` scaffolding, `/speckit-*` pipeline) |
