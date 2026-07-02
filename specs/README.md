# Ze Specs

Design and implementation specs for the Ze personal AI assistant.

## Structure

```
specs/
├── TEMPLATE.md        ← template directory (points to the three below)
├── TEMPLATE-phase.md  ← feature / phase spec template
├── TEMPLATE-adr.md    ← architecture decision record template
├── TEMPLATE-core.md   ← ze-core infrastructure module spec template
├── phases/            ← feature and phase implementation specs
├── core/              ← ze-core infrastructure layer specs
└── arch/              ← architecture decision records
```

## Writing a new spec

Pick the right template:

| What you are writing | Template | Destination |
|----------------------|----------|-------------|
| New feature or phase | `TEMPLATE-phase.md` | `phases/<next-number>-<name>.md` |
| New ze-core module | `TEMPLATE-core.md` | `core/<next-number>-<name>.md` |
| Cross-cutting design decision | `TEMPLATE-adr.md` | `arch/<name>.md` |

Copy the template, fill in the sections, and remove any that don't apply.

**Required sections by type:**
- Phase: Summary, Goals, Non-Goals, Alternatives Considered, Definition of Done
- ADR: Context and Problem Statement, Considered Options, Decision Outcome
- Core: Purpose, Responsibilities, Out of Scope

**Status is authoritative in the spec header.** The index tables below are
navigation aids — update both, but when they diverge the spec header wins.

All Open Questions must be resolved (or explicitly deferred with a target date)
before setting status → Done.

## Phase specs (`phases/`)

Legend: ✅ Done · 🔄 In Progress · 🔲 Pending · ⏸ Deferred · ⚠️ Deprecated

| # | Spec | Status |
|---|------|--------|
| 00 | [Overview](phases/00-overview.md) | ✅ Current |
| 01 | [Routing](phases/01-routing.md) | ✅ Done |
| 02 | [Capability Gate](phases/02-capability-gate.md) | ⚠️ Deprecated → `core/03` |
| 03 | [Memory](phases/03-memory.md) | ✅ Done |
| 04 | [Agents](phases/04-agents.md) | ⚠️ Deprecated → `core/01` |
| 05 | [Orchestration](phases/05-orchestration.md) | ✅ Done |
| 06 | [OpenRouter Client](phases/06-openrouter-client.md) | ✅ Done |
| 07 | [API](phases/07-api.md) | ✅ Done |
| 08 | [Telegram Bot](phases/08-telegram.md) | ✅ Done |
| 09 | [Agent & Tool API](phases/09-agent-tool-api.md) | ✅ Done |
| 10 | [Google Calendar + Gmail](phases/10-phase3-google.md) | ✅ Done |
| 11 | [Persona](phases/11-persona.md) | ✅ Done |
| 12 | [Workflow](phases/12-workflow.md) | ✅ Done |
| 13 | [Memory Consolidation](phases/13-phase5-memory.md) | ✅ Done |
| 14 | [User Profile](phases/14-user-profile.md) | ✅ Done |
| 15 | [Proactive Ze](phases/15-proactive-ze.md) | ✅ Done |
| 16 | [Insight Generation](phases/16-insight-generation.md) | ✅ Done |
| 17 | [Cost Telemetry](phases/17-cost-telemetry.md) | ✅ Done |
| 18 | [Cost-Aware Routing](phases/18-cost-aware-routing.md) | ✅ Done |
| 19 | [Multimodal Input](phases/19-multimodal-input.md) | ✅ Done |
| 20 | [Contacts](phases/20-contacts.md) | ✅ Done |
| 21 | [Telegram Commands](phases/21-telegram-commands.md) | ✅ Done |
| 22 | [Reminders Agent](phases/22-reminders-agent.md) | ✅ Done |
| 23 | [Eval](phases/23-eval.md) | ✅ Done |
| 24 | [Agentic Tool Loop](phases/24-agentic-tool-loop.md) | ✅ Done |
| 25 | [Persona Profiles + Dials](phases/25-persona-profiles.md) | ✅ Done |
| 26 | [Prospecting Agent](phases/26-prospecting-agent.md) | ✅ Done |
| 27 | [Channels](phases/27-channels.md) | ✅ Done |
| 28 | [Goal Engine](phases/28-goal-engine.md) | ✅ Done |
| 29 | [Progress Messages](phases/29-progress-messages.md) | ✅ Done |
| 30 | [Agent Harness](phases/30-agent-harness.md) | ✅ Done |
| 31 | [Goal Engine v2](phases/31-goal-engine-v2.md) | ✅ Done |
| 32 | [Goal Collaboration](phases/32-goal-collaboration.md) | ✅ Done |
| 33 | [Proactive Goal Suggestions](phases/33-goal-suggestions.md) | ✅ Done |
| 34 | [Stuck Goal Detection](phases/34-stuck-goal-detection.md) | ✅ Done |
| 35 | [Cross-Goal Output Reuse](phases/35-cross-goal-output-reuse.md) | ✅ Done |
| 36 | [Cross-Goal Learning Promotion](phases/36-cross-goal-learning-promotion.md) | ✅ Done |
| 37 | [News Package](phases/37-news-package.md) | ✅ Done |
| 38 | [News Personalization](phases/38-news-personalization.md) | ✅ Done |
| 39 | [News Credibility](phases/39-news-credibility.md) | ✅ Done |
| 40 | [Notifications](phases/40-notifications.md) | ✅ Done |
| 41 | [Component Descriptors](phases/41-component-descriptors.md) | ✅ Done |
| 42 | [Native UI Foundation](phases/42-native-ui-foundation.md) | ✅ Done |
| 43 | [React Web App](phases/43-react-web-app.md) | ✅ Done |
| 44 | [Calendar Package Split](phases/44-package-split-google-calendar-api.md) | ✅ Done |
| 46 | [Accountability Layer](phases/46-accountability-layer.md) | ✅ Done |
| 47 | [Plugin Framework](phases/47-plugin-framework.md) | ✅ Done (tool namespacing deferred) |
| 48 | [Ze Core Split](phases/48-core-split.md) | ✅ Done |
| 49 | [Ze SDK](phases/49-ze-sdk.md) | ✅ Done |
| 50 | [News Preference Model](phases/50-news-preferences.md) | ✅ Done |
| 51 | [Onboarding Platform](phases/51-onboarding.md) | ✅ Done |
| 52 | [Session-Grouped Episode Consolidation](phases/52-session-grouped-consolidation.md) | ✅ Done |
| 53 | [Eval Consolidation](phases/53-eval-consolidation.md) | ✅ Done |
| 54 | [Progress Messages](phases/54-progress-messages.md) | ✅ Done |
| 55 | [Signal Substrate](phases/55-signal-substrate.md) | ✅ Done |
| 56 | [Salience & Relevance Model](phases/56-salience-relevance-model.md) | ✅ Done |
| 57 | [Correlation Engine](phases/57-correlation-engine.md) | ✅ Done |
| 58 | [Inline Conversational Correlation](phases/58-inline-correlation.md) | ✅ Done |
| 59 | [Proactive Correlation Push](phases/59-proactive-correlation-push.md) | ⏸ Deferred (post-v1) |
| 60 | [Cross-Plugin Signal Contract](phases/60-signal-source-contract.md) | ✅ Done |
| 61 | [Convergence & Pressure Points](phases/61-convergence-pressure-points.md) | 🔲 Pending (design-only) |
| 62 | [Data Portability](phases/62-data-portability.md) | ✅ Done |
| 63 | [Integration Framework](phases/63-integration-framework.md) | ✅ Done |
| 64 | [Plugin Package Extraction](phases/64-plugin-package-extraction.md) | ✅ Done |
| 65 | [Eager Session Summaries](phases/65-eager-session-summaries.md) | ✅ Done |
| 66 | [Primitive UI](phases/66-primitive-ui.md) | ✅ Done |
| 67 | [Finance Plugin](phases/67-finance-plugin.md) | ✅ Done |
| 68 | [ze-data Package](phases/68-ze-data.md) | ✅ Done |
| 69 | [ze-ingestion Pipeline](phases/69-ze-ingestion.md) | ✅ Done |
| 70 | [Finance Recurring Detection](phases/70-finance-recurring.md) | ✅ Done |
| 71 | [Cross-Goal Awareness](phases/71-cross-goal-awareness.md) | 🔲 Pending |
| 72 | [API Client Codegen](phases/72-api-client-codegen.md) | ✅ Done |
| 73 | [API Surface](phases/73-api-surface.md) | ✅ Done |
| 74 | [Automation Substrate](phases/74-automation-substrate.md) | ✅ Done |
| 75 | [Server-Driven UI Package](phases/75-server-driven-ui-package.md) | ✅ Done |
| 76 | [ze-api Shell Cleanup](phases/76-ze-api-shell-cleanup.md) | ✅ Done |
| 77 | [ze-logging Package](phases/77-ze-logging.md) | ✅ Done |
| 78 | [Dream Memory](phases/78-dream-memory.md) | 🔄 In Progress |
| 79 | [NLI Cross-Encoder Integration](phases/79-nli-model.md) | ✅ Done |
| 80 | [NLI Client + Plugin Access](phases/80-nli-client.md) | ✅ Done |
| 81 | [Plugin NLI Adoption](phases/81-plugin-nli-adoption.md) | ✅ Done |
| 82 | [ze-web FSD Restructure](phases/82-ze-web-fsd.md) | ✅ Done |
| 83 | [ze-communication + ze-messenger](phases/83-ze-communication.md) | ✅ Done |
| 84 | [Webhook Infrastructure](phases/84-webhooks.md) | 🔲 Pending |
| 85 | [Ze Messaging Hub](phases/85-messaging-hub.md) | 🔲 Pending |
| 87 | [Plugin UI Platform](phases/87-plugin-ui.md) | ✅ Done |
| 88 | [Memory Feed](phases/88-memory-feed.md) | 🔲 Pending |
| 89 | [Message Trace](phases/89-message-trace.md) | 🔲 Pending |
| 90 | [Ze's Mind Split-Pane](phases/90-ze-mind-split-pane.md) | 🔲 Pending |
| 91 | [Goal Dashboard v2](phases/91-goal-dashboard-v2.md) | 🔲 Pending |
| 92 | [Agent Activity Heatmap](phases/92-agent-activity-heatmap.md) | ✅ Done |
| 93 | [Temporal Memory Timeline](phases/93-temporal-memory-timeline.md) | 🔲 Pending |
| 94 | [Memory Graph View](phases/94-memory-graph-view.md) | 🔲 Pending |
| 95 | [Unified Streaming Architecture](phases/95-live-trace-streaming.md) | 🔲 Pending |
| 96 | [Dev Data Seeder](phases/96-dev-data-seeder.md) | 🔲 Pending |
| 97 | [Embedding Model Upgrade (MiniLM → E5)](phases/97-embedding-model-upgrade.md) | 🔲 Pending |
| 98 | [Workflow Run Chat](phases/98-workflow-run-chat.md) | 🔲 Pending |
| 99 | [Multi-Conversation Support](phases/99-multi-conversation.md) | 🔲 Pending |
| 101 | [Session Search & Titles](phases/101-session-search.md) | ✅ Done |

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
