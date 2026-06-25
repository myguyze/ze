# Ze — Package Architecture

Ze is a monorepo organised into five top-level directories with a strict one-way dependency graph.
Understanding the split makes it clear where new code belongs and how the pieces fit.

---

## Layout

```
ze/
├── core/             # Shared infrastructure — no domain knowledge
│   ├── ze-agents/    # Developer API — BaseAgent, @agent, @tool, ZePlugin, shared types
│   ├── ze-plugin/    # Plugin extension framework — ZePlugin, channels, signal sources, data domains
│   ├── ze-proactive/ # Job scheduling framework — ProactiveScheduler, ProactiveNotifier
│   ├── ze-automation/# Core automation engine — goals, workflows, accountability, agents, jobs
│   ├── ze-sdk/       # Public SDK surface — flat re-export layer for plugin authors
│   ├── ze-core/      # Engine — routing, orchestration, telemetry, DI container
│   ├── ze-data/      # Data portability layer — DataDomain, export/import/delete orchestration
│   ├── ze-memory/    # Memory package — facts, episodes, graph, retrieval
│   ├── ze-onboarding/# Onboarding coordinator, provider contracts, reset domain types
│   ├── ze-ingestion/ # Content ingestion pipeline — fetch, process, extract, archive
│   ├── ze-correlation/ # Cross-domain hypothesis engine — inline and proactive correlation
│   ├── ze-browser/   # Browser sidecar HTTP client
│   ├── ze-notifications/ # Push notification abstraction (ntfy)
│   └── ze-components/    # Server-driven UI component descriptors
├── integrations/     # External service wrappers — no Ze domain knowledge
│   └── ze-google/    # Google OAuth2 credentials and service client factories
│   └── ze-trading212/ # Trading212 REST client for finance ingestion
├── plugins/          # ZePlugin domain extensions
│   ├── ze-personal/  # Personal-assistant domain layer — persona, contacts, onboarding
│   ├── ze-email/     # Gmail channel + email agent (ZePlugin)
│   ├── ze-prospecting/   # Prospecting agent, campaign store, recovery job (ZePlugin)
│   ├── ze-calendar/  # Calendar + reminders domain (ZePlugin)
│   ├── ze-news/      # News ingestion, ranking, credibility (ZePlugin)
│   └── ze-finance/   # Finance domain (ZePlugin)
├── packages/         # Shared npm packages (Bun workspace)
│   └── ze-client/    # @ze/client — generated typed SDK for ze-web
└── apps/             # Deployment units
    ├── ze-api/       # HTTP/WebSocket API, wires all plugins
    └── ze-web/       # React web client (Vite + TypeScript + Tailwind + shadcn/ui)
```

### Dependency graph

```
ze-browser        ←  no ze deps
ze-onboarding     ←  no ze deps               ← setup coordinator, provider/store/persistence protocols
ze-agents         ←  ze-onboarding            ← developer API (BaseAgent, @agent, @tool, ZePlugin, types)
ze-plugin         ←  ze-agents                ← plugin extension framework, channels, signal sources, data domains
ze-proactive      ←  ze-agents                ← job scheduling framework
ze-data           ←  no ze deps               ← portability descriptor + service layer
ze-notifications  ←  no ze deps
ze-components     ←  ze-agents
ze-google         ←  no ze deps               ← integrations/
ze-trading212     ←  no ze deps
ze-memory         ←  ze-agents
ze-ingestion      ←  ze-agents, ze-memory, ze-browser
ze-correlation    ←  ze-agents, ze-memory
ze-automation     ←  ze-agents, ze-proactive, ze-memory   ← goals, workflows, accountability; wired directly by ze-api
ze-sdk            ←  ze-agents, ze-proactive, ze-memory, ze-onboarding, ze-plugin, ze-data, ze-automation   ← plugin entry point
ze-core           ←  ze-agents, ze-plugin                ← engine; never a domain dep
ze-personal       ←  ze-sdk
ze-email          ←  ze-sdk, ze-google, ze-personal
ze-prospecting    ←  ze-sdk, ze-browser, ze-personal
ze-calendar       ←  ze-sdk, ze-google, ze-personal
ze-news           ←  ze-sdk
ze-finance        ←  ze-sdk, ze-trading212
ze-api            ←  ze-core, ze-plugin, ze-data, ze-sdk, ze-automation, ze-personal, ze-email,
                      ze-prospecting, ze-calendar, ze-google, ze-browser, ze-news, ze-finance,
                      ze-notifications, ze-components, ze-onboarding, ze-ingestion, ze-correlation
ze-client         ←  no ze deps (generated from ze-api spec; npm workspace only)
ze-web            ←  ze-client (workspace:*), connects to ze-api over WebSocket/REST
```

Hard rules:
- `ze-onboarding` never imports from any other Ze package — it is the stable setup-flow foundation.
- `ze-agents` depends only on `ze-onboarding` plus third-party utilities — it is the stable agent/plugin API foundation.
- `ze-plugin` and `ze-data` stay free of application wiring; they own the reusable extension and portability seams.
- `ze-core` never imports from domain packages. It depends on `ze-agents` and `ze-plugin` for shared engine-facing types.
- Plugin packages (`ze-personal`, `ze-email`, etc.) never import `ze-core` directly — use `ze-sdk`.
- `ze-memory`, `ze-automation`, and `ze-personal` never import from `ze-api`. Violations break the abstraction.

---

## ze-agents — Developer API

`ze_agents` is the stable authoring API. Plugin authors import everything they need from
`ze_sdk`, which re-exports `ze_agents` symbols and the onboarding contract.

| Module | What it provides |
|--------|-----------------|
| `base_agent.py` | `BaseAgent` ABC with `agentic_loop`, `call_tool`, `emit`, `_build_system_prompt` |
| `registry.py` | `@agent` decorator + `AgentRegistry` |
| `tool.py` | `@tool` decorator, `ToolAccess` enum |
| `plugin.py` | `ZePlugin` ABC — container and graph extension seam |
| `onboarding/` | Compatibility re-export of `ze_onboarding` onboarding symbols |
| `types.py` | `AgentContext`, `AgentResult`, `ToolCall`, `GateDecision`, `Mode`, `AbortToken` |
| `client.py` | `LLMClient` Protocol — the interface `BaseAgent` calls; `OpenRouterClient` satisfies it |
| `nli.py` | `NLIClient` Protocol — local cross-encoder entailment/contradiction; `LocalNLIClient` satisfies it |
| `db.py` | `DBPool` Protocol — structural type for asyncpg pools |
| `channels/` | `Channel` ABC, `ChannelRegistry`, `ChannelType`, `Message`, `SentMessage`, `Thread` |
| `interface/` | `AppInterface` ABC, `InputPreprocessor`, `Action`, `Notification` |
| `progress/` | `ProgressReporter`, locale translations |
| `hooks.py` | `HarnessHook` ABC — step-level abort, pre/post tool hooks |
| `errors.py` | Typed `ZeError` exception hierarchy |
| `logging.py` | `get_logger(__name__)` wrapper |
| `settings.py` | `Settings` dataclass — config bridge |
| `defaults.py` | Framework-level constants (model names, thresholds) |

---

## ze-proactive — Job Scheduling Framework

`ze_proactive` owns the scheduling and notification plumbing for background jobs.
Depends on `ze-agents` only.

| Module | What it provides |
|--------|-----------------|
| `job.py` | `ProactiveJob` Protocol, `@proactive_job` decorator |
| `scheduler.py` | `ProactiveScheduler` — APScheduler wrapper |
| `notifier.py` | `ProactiveNotifier` — push delivery via ntfy/WebSocket |
| `push_log_store.py` | `PushLogStore`, `PushLogEntry` — delivery audit log |

---

## ze-sdk — Public SDK Surface

`ze_sdk` is a flat re-export layer over `ze-agents`, `ze-proactive`, `ze-memory`,
`ze-onboarding`, `ze-plugin`, `ze-data`, and `ze-automation`.
Plugin authors list `ze-sdk` as their only Ze dependency and import everything from it.
`ze-core` never appears in a plugin's dependency list.

| Module | What it re-exports |
|--------|-----------------|
| `ze_sdk` | `ZePlugin`, `agent`, `tool`, `ToolAccess`, `BaseAgent`, `get_logger`, `Settings`, `DBPool` |
| `ze_sdk.types` | `AgentContext`, `AgentResult`, `ToolCall`, `GateDecision`, `Mode`, `AbortToken`, `Action`, `Notification` |
| `ze_sdk.proactive` | `ProactiveJob`, `proactive_job`, `ProactiveScheduler`, `ProactiveNotifier`, `PushLogStore`, `PushLogEntry` |
| `ze_sdk.channels` | `Channel`, `ChannelType`, `ChannelHandle`, `Message`, `SentMessage`, `Thread`, `ThreadMessage`, `ChannelSendError` |
| `ze_sdk.memory` | `MemoryContext`, `Fact`, `Episode`, `Procedure`, `Entity`, `TaskState`, `RetrievalRequest`, `MemoryStore`, `PostgresMemoryStore` |
| `ze_sdk.onboarding` | `OnboardingProvider`, `OnboardingStep`, `OnboardingField`, `OnboardingSeed`, `OnboardingResult`, setup seed and submission types |
| `ze_sdk.automation` | `Goal`, `GoalStatus`, `GoalStore`, `GoalSuggestionStore`, `Workflow`, `WorkflowStep`, `WorkflowStore`, `WorkflowScheduler`, `AutomationPlanner`, `AutomationStore` |
| `ze_sdk.errors` | Full `ZeError` hierarchy |

---

## ze-onboarding — Setup Flow

`ze_onboarding` owns the reusable onboarding domain: provider contracts, step/seed
dataclasses, coordinator flow, review-before-save behavior, and reset scope/result
types. It has no Ze dependencies. It does not know about Postgres, WebSocket, FastAPI,
memory stores, or the web client.

| Module | What it provides |
|--------|-----------------|
| `types.py` | `OnboardingProvider`, `OnboardingStep`, `OnboardingSeed`, `OnboardingStore`, `OnboardingPersistence`, `ResetScope` |
| `coordinator.py` | `OnboardingCoordinator` — orders providers, dispatches submissions, inserts review step, applies approved seeds through protocols |
| `providers.py` | `CoreOnboardingProvider` — minimal built-in setup for name/timezone |

Concrete adapters live elsewhere:

- `ze_api.onboarding.store` implements the `OnboardingStore` protocol with Postgres.
- `ze_api.onboarding.persistence` applies approved seeds to memory/plugin stores.
- `ze_api.onboarding.reset` executes SQL reset scopes.
- `ze_api.api.ws` maps WebSocket commands and `component_submit` frames to the coordinator.

---

## ze-core — Engine

`ze_core` owns the LangGraph engine, routing infrastructure, telemetry, and DI
container. It depends on `ze-agents` for the developer API types but never on domain
packages. Plugin authors never import `ze_core` directly — use `ze_sdk` instead.

| Module | What it provides |
|--------|-----------------|
| `orchestration/` | LangGraph graph builder, node implementations, `AgentState` (graph-private), edges |
| `routing/` | `EmbeddingRouter`, `ComplexityEstimator`, `RoutingFallback` |
| `capability/` | `CapabilityGate`, `PostgresCapabilityOverrideStore` |
| `conversation/` | Message/session/confirmation stores + graph turn helpers (`turn.py`) |
| `openrouter/` | `OpenRouterClient` (satisfies `LLMClient` Protocol), streaming, transcription |
| `telemetry/` | `CostTracker`, `CostReconciler`, `PostgresCostStore`, context vars |
| `embeddings.py` | Shared `paraphrase-multilingual-MiniLM-L12-v2` singleton |
| `nli.py` | `LocalNLIClient` — `cross-encoder/nli-deberta-v3-small` singleton (satisfies `NLIClient`) |
| `container.py` | Base `Container` with DI wiring, plugin support |

**Rule of thumb:** `ze-core` owns everything that powers the engine at runtime but
that plugin authors should never need to import. If the symbol belongs in the stable
authoring API, it goes in `ze-agents`. If it's a job framework primitive, it goes in
`ze-proactive`.

---

## ze-plugin — Extension Framework

`ze_plugin` owns the reusable plugin seam: `ZePlugin`, channels, signal sources, and
the integration protocol shared by engine and plugin code. It depends on `ze-agents`
only and stays free of application wiring.

| Module | What it provides |
|--------|-----------------|
| `plugin.py` | `ZePlugin`, `DataDomain` re-export for backwards compatibility |
| `channels/` | `Channel` ABC, handle/message types, `ChannelRegistry` |
| `signals.py` | `SignalSource` protocol for cross-plugin signal collection |
| `integration.py` | `ZeIntegration` protocol for third-party credential classes |
| `registry.py` | Plugin registry helpers |

---

## ze-data — Data Portability

`ze_data` owns the portability contract and service layer for export/import/delete.
It has no Ze package dependencies and is reused by `ze-plugin` and `ze-sdk`.

| Module | What it provides |
|--------|-----------------|
| `domain.py` | `DataDomain` dataclass |
| `portability/service.py` | `DataPortabilityService` |
| `portability/assembler.py` | ZIP export/import assembly helpers |
| `portability/types.py` | Export/import result types |
| `errors.py` | Typed portability errors |

---

## ze-ingestion — Content Ingestion

`ze_ingestion` owns the generic content ingestion pipeline. It depends on `ze-agents`,
`ze-memory`, and `ze-browser`.

| Module | What it provides |
|--------|-----------------|
| `classifier.py` | `ContentClassifier` |
| `fetchers/` | Web/browser fetchers and plugin extension points |
| `processors/` | HTML, PDF, audio, image, and text processors |
| `extractors/` | `Extractor` protocol and default `LLMExtractor` |
| `pipeline.py` | `IngestionPipeline` |
| `store.py` | `IngestionStore` |
| `sink.py` | `MemorySink` |
| `agent.py` | `IngestionAgent` + ingestion tools |

---

## ze-correlation — Signal Correlation

`ze_correlation` owns cross-domain hypothesis generation from memory and signal
inputs. It depends on `ze-agents` and `ze-memory`.

| Module | What it provides |
|--------|-----------------|
| `engine.py` | `CorrelationEngine` |
| `store.py` | `PostgresHypothesisStore` |
| `job.py` | `CorrelationJob` |
| `push.py` | `CorrelationPushConsumer` |
| `prompts.py` | Prompt templates for hypothesis generation |
| `types.py` | Hypothesis and evidence types |

---

## ze-memory — Memory Package

`ze_memory` owns all memory persistence, retrieval, and consolidation logic. It
depends on `ze-agents` for logging and settings abstractions.

| Module | What it provides |
|--------|-----------------|
| `retriever.py` | `PostgresMemoryStore` — the central memory store implementing the full MemoryStore protocol |
| `consolidator.py` | `MemoryConsolidator` — nightly fact dedup, expiry, episode archival, profile synthesis |
| `extractor.py` | `gather_fact_proposals` — LLM-driven fact extraction from conversation turns |
| `policies.py` | `DefaultPolicyRegistry` — maps module names to retrieval policies |
| `projection.py` | Budget-aware result projection — `budget_facts`, `budget_episodes`, `facets_from_rows` |
| `types.py` | `Fact`, `Episode`, `Event`, `Procedure`, `TaskState`, `ProfileFacet`, `MemoryContext`, `RetrievalRequest` |
| `defaults.py` | Consolidation thresholds and retrieval defaults |
| `graph/store.py` | `PostgresGraphStore` — relationship storage and expansion |
| `graph/traversal.py` | `BoundedExpansionPolicy` — one-hop graph context enrichment |
| `graph/predicates.py` | Typed relationship predicates: `DESCRIBES`, `SOURCED_FROM`, `MENTIONS`, `BELONGS_TO_GOAL`, … |
| `graph/types.py` | `Relationship`, `GraphExpansion` |
| `graph/projection.py` | `enrich_context` — merge graph expansion results into `MemoryContext` |

---

## ze-automation — Core Automation Engine

`ze_automation` owns the complete automation stack as a first-class core package. It
is wired directly into `ze_api/container.py` — not via the plugin registry — so goals
and workflows are always present. It depends on `ze-agents`, `ze-proactive`, and
`ze-memory`.

| Module | What it provides |
|--------|-----------------|
| `goals/types.py` | `Goal`, `Milestone`, `VerificationGate`, `GoalLearning`, `GoalSuggestion`, `ExecutionTrace`, enums |
| `goals/store.py` | `GoalStore` Protocol |
| `goals/postgres.py` | `PostgresGoalStore` |
| `goals/suggestion_store.py` | `GoalSuggestionStore`, `PostgresGoalSuggestionStore` |
| `goals/planner.py` | `GoalPlanner` — LLM-driven milestone decomposition, replanning, retrospective, suggestion synthesis |
| `goals/executor.py` | `GoalExecutor` — advance loop, gate handling, steering, learning extraction |
| `workflow/types.py` | `Workflow`, `WorkflowStep`, `WorkflowExecution`, `StepResult` |
| `workflow/store.py` | `WorkflowStore` Protocol |
| `workflow/postgres.py` | `PostgresWorkflowStore` |
| `workflow/scheduler.py` | `WorkflowScheduler` — APScheduler cron/date job management |
| `workflow/planner.py` | `WorkflowPlanner` — LLM-driven step decomposition and schedule parsing |
| `agents/goals/` | `GoalAgent` — conversational goal lifecycle |
| `agents/workflow/` | `WorkflowManagerAgent` — conversational workflow management |
| `jobs/goal_narrative.py` | Weekly goal narrative job |
| `jobs/goal_suggestion.py` | Weekly goal suggestion job |
| `jobs/stuck_goals.py` | Stuck goal detection job |
| `jobs/accountability.py` | `AccountabilityJob` — weekly activity + cost narrative |
| `jobs/cost_anomaly.py` | `CostAnomalyJob` — per-run cost spike detection |
| `accountability/` | `AccountabilityStore`, `ActivitySummary`, `AnomalyRecord`, `build_narrative` |
| `graph/routing_context.py` | Goal-aware routing context injection |
| `runtime/contracts.py` | `AutomationPlanner`, `AutomationStore` protocols |
| `migrations/versions/` | `zc006`–`zc009` (goal traces/suggestions/stuck/reuse), `zc011` (workflows), `zc014` (accountability) |

Agent registration is exposed via `ze_automation.agent_module_paths()`, imported in
`ze-api`'s container alongside plugin paths from `ZePlugin.agent_module_paths()`.

---

## ze-personal — Domain Layer

`ze_personal` owns persona, contacts, and onboarding — the parts of the personal
assistant that are specific to this user's identity and social graph. It depends on
`ze-sdk` and knows nothing about Google APIs or HTTP. Goals, workflows, and
accountability live in `ze-automation`, not here.

| Module | What it provides |
|--------|-----------------|
| `persona/` | `PostgresPersonaStore`, `build_identity_block`, named profiles, dial overrides |
| `contacts/` | `PersonStore`, `ContactChannelStore`, extractors, consolidator, tools |
| `agents/research/` | `ResearchAgent` — web search and synthesis |
| `agents/companion/` | `CompanionAgent` — reasoning and conversation |
| `jobs/briefing.py` | Morning briefing job |
| `jobs/insights.py` | Weekly insight generation job |
| `jobs/contacts.py` | Contact review suggestions job |
| `graph/workflow.py` | `build_workflow_graph()` — workflow execution graph (LangGraph wiring) |
| `graph/memory_hooks.py` | Post-memory-write hooks (e.g. contact extraction) |
| `plugin.py` | `PersonalPlugin(ZePlugin)` — wires persona + contacts into ze-core |

---

## ze-email — Email Domain

`ze_email` owns the Gmail channel and email agent. It depends on `ze-sdk`, `ze-google`,
and `ze-personal` (for contact extraction from email tool calls).

| Module | What it provides |
|--------|-----------------|
| `channel/gmail.py` | `GmailChannel` — Gmail API send/receive/poll |
| `agents/email/agent.py` | `EmailAgent` — inbox read, draft, send |
| `agents/email/tools.py` | Gmail `@tool` functions |
| `plugin.py` | `EmailPlugin(ZePlugin)` — registers agent when Google credentials are present |

---

## ze-prospecting — Prospecting Domain

`ze_prospecting` owns autonomous prospect research, campaign persistence, and stale
campaign recovery. It depends on `ze-sdk`, `ze-browser`, and `ze-personal`.

| Module | What it provides |
|--------|-----------------|
| `agents/agent.py` | `ProspectingAgent` — research + outreach drafting |
| `agents/tools.py` | `add_prospect`, `draft_outreach`, `log_outreach_event` tools |
| `store.py` | `ProspectCampaignStore` — campaign and outreach persistence |
| `jobs/campaigns.py` | `recover_stale_campaigns` — marks hung campaigns as failed |
| `plugin.py` | `ProspectingPlugin(ZePlugin)` — registers agent, store, and recovery job |

---

## ze-calendar — Calendar Domain

`ze_calendar` owns the calendar and reminders domain. It depends on `ze-sdk`,
`ze-google` (for credentials), and `ze-personal`.

| Module | What it provides |
|--------|-----------------|
| `agents/calendar/` | `CalendarAgent` — Google Calendar CRUD |
| `agents/reminders/` | `RemindersAgent` — NL time parsing, APScheduler firing |
| `reminders/store.py` | `ReminderStore` — reminder persistence |
| `reminders/calendar.py` | `CalendarReminderService` — Google Calendar sync and reminder scheduling |
| `reminders/calendar_store.py` | `CalendarReminderStore` — synced event persistence |
| `timezone/` | `TimezoneService`, `world_time` `@tool` |
| `jobs/calendar_reminder.py` | `CalendarReminderJob` — daily sync cron job |
| `plugin.py` | `CalendarPlugin(ZePlugin)` — registers agents and services |

---

## ze-google — Shared Google Credentials

`ze_google` provides a thin credential layer. It has no Ze dependencies and can be
imported by any package that needs Google OAuth2.

| Module | What it provides |
|--------|-----------------|
| `auth.py` | `GoogleCredentials`, `SCOPES`, service client factories |

---

## ze-trading212 — Trading212 Client

`ze_trading212` is a thin HTTP client for the Trading212 REST API. It has no Ze
dependencies and is consumed by `ze-finance`.

| Module | What it provides |
|--------|-----------------|
| `client.py` | Async Trading212 API client |

---

## ze-news — News Package

`ze_news` owns news ingestion, personalised ranking, and credibility analysis.
Depends on `ze-sdk` only.

| Module | What it provides |
|--------|-----------------|
| `agents/news/` | `NewsAgent` — headlines and search tools |
| `jobs/fetch.py` | `NewsFetchJob` — RSS ingestion and embedding |
| `store.py` | `NewsStore` — article persistence + pgvector search |
| `registry.py` | `build_registry()` — source registry from config |
| `credibility.py` | LLM-based article credibility scoring |
| `personalization.py` | Interest-vector-based ranking |
| `plugin.py` | `NewsPlugin(ZePlugin)` — registers agent, conditionally loaded |

---

## ze-finance — Finance Domain

`ze_finance` owns portfolio positions, bank transactions, spending summaries,
recurring detection, and proactive P&L alerts. It depends on `ze-sdk` and
`ze-trading212`, and its finance-specific LLM calls are pinned to Anthropic via
OpenRouter.

| Module | What it provides |
|--------|-----------------|
| `agents/finance/` | `FinanceAgent` and its finance tools |
| `categoriser.py` | `CategoryInferrer` — keyword rules + optional LLM categorisation |
| `jobs/snapshot.py` | `DailySnapshotJob` — syncs data sources, categorises, emits signals |
| `jobs/recurring.py` | `RecurringDetectionJob` — recurring-charge detection and nudges |
| `plugin.py` | `FinancePlugin(ZePlugin)` — registers agent, jobs, signal source, and data domains |
| `recurring/` | Recurring expense types, detector, and store |
| `signals/finance.py` | `FinanceSignalSource` — emits finance signals into Ze |
| `sources/trading212.py` | Trading212 ingestion backend |
| `sources/csv.py` | CSV bank-statement import backend |
| `store.py` | Portfolio, transaction, and CSV mapping stores |
| `types.py` | Finance domain datatypes |

---

## ze-browser — Sidecar Client

`ze_browser` is a thin HTTP client for the browser sidecar service (Playwright + FastAPI
running as a separate process). It has no ze dependencies.

| Module | What it provides |
|--------|-----------------|
| `client.py` | `BrowserClient` — `httpx`-based async client |
| `tool.py` | `@tool`-registered `browse_url` tool |
| `types.py` | `BrowserResult` |
| `errors.py` | `BrowserError` |

The sidecar itself is deployed separately and is never imported by any Python package.

---

## ze-notifications — Push Notifications

`ze_notifications` provides a transport-agnostic push notification abstraction.
No ze dependencies.

| Module | What it provides |
|--------|-----------------|
| `notifier.py` | `Notifier` ABC |
| `ntfy.py` | `NtfyNotifier`, `NtfyConfig` — ntfy.sh/self-hosted ntfy implementation |
| `types.py` | `Notification` |

---

## ze-components — Server-Driven UI

`ze_components` defines server-driven UI component descriptors sent to the React web app
inside message frames. No ze dependencies.

| Module | What it provides |
|--------|-----------------|
| `types.py` | Component descriptor dataclasses |
| `tools.py` | `@tool`-registered render helpers (imported at startup for side effects) |

---

## ze-api — Application Shell

`ze_api` is the runnable deployment unit. It contains **no domain agents or jobs** —
only wiring, transport, and configuration. It depends on all Ze packages and registers
their `ZePlugin` implementations.

| Module | What it provides |
|--------|-----------------|
| `api/` | FastAPI app, WebSocket endpoint (`/ws`), REST routes, message route |
| `interface/native.py` | `NativeAppInterface` — WebSocket + ntfy delivery |
| `container.py` | `ZeContainer` — composition entry; subclasses `ze_core.Container` |
| `compose.py` | `register_all_proactive_jobs()` — core + plugin cron registration |
| `migrate.py` | Meta-migrator — discovers all package migration paths; ze-api owns no tables |
| `settings.py` | `ZeApiSettings` — shell env + YAML; `to_core_settings()` bridge |
| `migrations/env.py` | Alembic runner harness (no owned revision files) |

Harness hooks (`ToolCallCapHook`, `ComponentCollectionHook`) live in `ze_agents` and
`ze_components`; registered via `ze_core/bootstrap.py`. Plugin and agent bootstrap live
in `ze_plugin/bootstrap.py` and `ze_agents/bootstrap.py` — not in ze-api.

Phase 76 moved domain bootstrap into package modules (`ze_automation/bootstrap`,
`ze-memory/bootstrap`, etc.). See
[specs/phases/76-ze-api-shell-cleanup.md](../specs/phases/76-ze-api-shell-cleanup.md).

---

## ze-client — Typed Frontend SDK

`@ze/client` (`packages/ze-client/`) is a local npm workspace package that exposes
the entire ze-api REST + WebSocket surface as typed TypeScript. `ze-web` is the only
consumer; no other package depends on it.

| Module | What it provides |
|--------|-----------------|
| `src/generated/sdk.gen.ts` | Named SDK functions generated from FastAPI `operation_id` values |
| `src/generated/types.gen.ts` | All REST request/response types |
| `src/generated/ws.ts` | WS frame types from `json-schema-to-typescript` |
| `src/client.ts` | `configure({ serverUrl, apiKey })` — sets the module-level default client; `createZeClient()` for explicit client construction |
| `src/blob.ts` | Hand-written helpers: `downloadExport`, `importArchive`, `healthCheck` |
| `src/error.ts` | `ApiError` class |
| `src/index.ts` | Re-exports everything above |

**Regenerating:** Run `bun run scripts/codegen.ts` after changing any FastAPI route,
operationId, or request/response schema. Generated files are committed.

**Auth pattern in ze-web:**

```typescript
// main.tsx — called once at startup
import { applyConfig } from "@/lib/client";
applyConfig();

// any page — no route strings, no auth boilerplate
import { listContacts } from "@ze/client";
const { data } = await listContacts();
```

---

## ze-web — React Client

`ze-web` is the React web application (Vite + TypeScript + Tailwind + shadcn/ui). It
communicates with `ze-api` via WebSocket at `/ws` and REST via `@ze/client`.
It has no Python dependencies — built and run with Bun.

```bash
make web-install   # bun install
make web           # dev server on :5173
make web-build     # production build
make web-test      # vitest
```

---

## The ZePlugin Extension Point

`ZePlugin` is the seam that lets domain packages inject behaviour into the engine
without `ze-core` knowing about them. It lives in `ze_agents.plugin` and is imported
via `ze_sdk`.

```python
from ze_sdk import ZePlugin

class ZePlugin(ABC):
    # Container-level hooks
    def agents(self) -> list[type[BaseAgent]]: ...
    def jobs(self) -> list[ProactiveJob]: ...
    def migrations_path(self) -> Path | None: ...

    # Graph-level hooks (applied at build time)
    def state_extensions(self) -> type | None: ...
    def graph_nodes(self) -> dict[str, Callable]: ...
    def graph_edges(self, builder: StateGraph) -> None: ...
    def configurable_services(self) -> dict[str, Any]: ...
    def agent_module_paths(self) -> list[str]: ...

    # Graph node hooks
    def register_proactive_jobs(self, scheduler, settings, *, consolidation_enabled=True): ...
```

Five plugins are registered in `ze_api/container.py`:

- **`PersonalPlugin`** (`ze_personal/plugin.py`) — identity builder, contact extraction
  hooks, research/companion agents, and proactive jobs (briefing, insights, contact review).
  Goals, workflows, and accountability are wired directly by `ze_api/container.py` via
  `ze_automation`, not through this plugin.
- **`EmailPlugin`** (`ze_email/plugin.py`) — Gmail channel + email agent (when Google
  credentials are configured).
- **`ProspectingPlugin`** (`ze_prospecting/plugin.py`) — prospecting agent, campaign store,
  stale campaign recovery job.
- **`CalendarPlugin`** (`ze_calendar/plugin.py`) — calendar and reminders agent paths.
- **`NewsPlugin`** (`ze_news/plugin.py`) — conditionally loaded when `news.enabled: true`
  and sources are configured.

### Adding a new plugin

1. Create a `ZePlugin` subclass in your package.
2. Declare the entry point in `pyproject.toml` under `[project.entry-points."ze.plugins"]`.
3. Add the package to `apps/ze-api/pyproject.toml` dependencies.
4. Override plugin hooks as needed — all methods have no-op defaults.

Plugins are discovered via entry points, topologically sorted by `depends_on`, and
instantiated through the shared dep map. Graph state extensions, memory policies,
checkpoint serde modules, REST stores, and proactive jobs are collected from each
plugin at startup — no manual list in `build_graph()`.

If your plugin constructor requires a new shared service type (e.g. a domain store
built before plugin discovery), add it to `plugin_deps` in `build_container()`.
Agent-scoped deps can be contributed via `agent_deps()` without touching the container.

---

## Where does new code go?

| New code | Package |
|----------|---------|
| New stable authoring API type or protocol | `ze-agents` (re-export from `ze_sdk`) |
| New job scheduling primitive | `ze-proactive` (re-export from `ze_sdk.proactive`) |
| New onboarding step/seed type, provider contract, or coordinator behavior | `ze-onboarding` (re-export from `ze_sdk.onboarding`) |
| New engine primitive (routing, graph node, telemetry) | `ze-core` |
| New memory retrieval policy for a plugin agent | plugin `memory_policies()` hook — not `ze-memory/policies.py` |
| New domain concept tied to personal assistant | `ze-personal` |
| New automation concept (goals, workflows, execution) | `ze-automation` |
| New Google integration credential | `ze-google` |
| New agent (general assistant: research, companion) | `ze-personal` → `ze_personal/agents/<name>/` |
| New agent (email) | `ze-email` → `ze_email/agents/<name>/` |
| New agent (prospecting) | `ze-prospecting` → `ze_prospecting/agents/` |
| New agent that needs calendar/reminder state | `ze-calendar` → `ze_calendar/agents/<name>/` |
| New agent that works with goals or workflows | `ze-automation` → `ze_automation/agents/<name>/` |
| New background job (automation: goals, workflows, costs) | `ze-automation` → `ze_automation/jobs/` |
| New background job (personal assistant: briefing, insights) | `ze-personal` → `ze_personal/jobs/` + `PersonalPlugin.register_proactive_jobs()` |
| New background job (prospecting) | `ze-prospecting` → `ze_prospecting/jobs/` + `ProspectingPlugin.register_proactive_jobs()` |
| New channel implementation (LinkedIn, WhatsApp) | New package or existing domain package → `channel/` module |
| New push notification backend | `ze-notifications` |
| New server-driven UI component | `ze-components` |
| Headless browser interaction | `ze-browser` |

When in doubt: ask whether the code has a runtime dependency on `ze-personal` or
application config. If yes, it belongs in `ze-api`. If it is part of the stable
authoring API, it belongs in `ze-agents` (accessible via `ze_sdk`). If it is
an automation concept (goals, workflows, execution state, cost reporting), it belongs
in `ze-automation`. If it is a personal-assistant concept (persona, contacts,
onboarding), it belongs in `ze-personal`.

---

## When to create a new package

Most features do not need a new package. The default answer is **no** — add code to
an existing package. A new package earns its existence only when it satisfies specific
criteria.

### Signals that a new package is warranted

**Independent deployment boundary.** The code must be deployable, testable, or
replaceable in isolation from the rest of Ze. `ze-browser` exists because the
Playwright sidecar runs as a separate process — the client needs no Ze knowledge.
`ze-notifications` exists because the push transport may be swapped (ntfy today,
APNs tomorrow) without touching any domain code.

**Zero or very narrow upward dependencies.** A package that depends on everything
can never be extracted cleanly. The new package should sit at a natural layer
boundary with a clear, minimal import surface. If you find yourself importing from
`ze-api` or `ze-personal` inside the new package, it probably belongs in one of them
instead.

**A coherent, named domain.** `ze-calendar` exists because calendar + reminders is
a recognisable product subsystem with its own agents, store, jobs, and Google API
surface. `ze-memory` exists because memory is a foundational concern that multiple
packages depend on and that has its own migration history, types, and retrieval
semantics. "I have five new files" is not a domain.

**A `ZePlugin` implementation makes sense.** If the new subsystem contributes agents,
graph nodes, configurable services, or proactive jobs — and those contributions should
be togglable without touching `ze-core` or `ze-personal` — a plugin is the right
contract. If the subsystem does not need any of those seams, it probably should not
be a plugin-backed package.

### Signals that code belongs in an existing package

- It is a new agent that uses goals or workflow state.
  → `ze-automation` → `ze_automation/agents/<name>/`.
- It is a new agent that uses contacts or persona.
  → `ze-personal` → `ze_personal/agents/<name>/`.
- It is a new proactive job tied to automation (goals, workflows, costs).
  → `ze_automation/jobs/`.
- It is a new proactive job tied to personal assistant domain logic (briefing, insights).
  → `ze_personal/jobs/` + `PersonalPlugin.register_proactive_jobs()`.
- It is a new memory retrieval policy or graph predicate.
  → `ze-memory`.
- It is a new domain concept that belongs alongside existing personal assistant logic.
  → `ze-personal`.
- It is "calendar-adjacent" — it uses `GoogleCredentials` or calendar stores.
  → `ze-calendar`.

### The subsystem model

Ze thinks of each non-core package as a **subsystem**: a self-contained slice of
functionality with its own agents, stores, jobs, and migration path, stitched into
the graph through `ZePlugin`.

A subsystem should be able to answer "yes" to all three of these:

1. **Does it have its own Postgres tables?** (its own `migrations/versions/`)
2. **Does it contribute at least one agent or job?** (registered via plugin)
3. **Could you disable it** (`enabled: false` in config or by not registering the
   plugin) **without breaking the rest of Ze?**

If the answer to any of these is "no", the code is not a subsystem — it is a feature
that belongs inside an existing package.

### Practical checklist before creating a new package

- [ ] The new package has a name that describes a coherent domain, not an implementation detail.
- [ ] It does not import from `ze-api`, `ze-personal`, or any package above it in the dependency graph.
- [ ] It owns at least one Postgres migration.
- [ ] It has a `plugin.py` implementing `ZePlugin` (unless it is a pure library like `ze-google` or `ze-browser`).
- [ ] Adding or removing the plugin from `ze_api/container.py` requires no other code changes.
- [ ] It has its own `pyproject.toml` and `tests/` directory.
- [ ] A spec in `specs/phases/` or `specs/arch/` exists before any code is written.
