# Ze Specs

Design and implementation specs for the Ze personal AI assistant.

## Structure

```
specs/
├── TEMPLATE.md       ← template for new specs
├── phases/           ← feature and phase implementation specs (00–46)
├── core/             ← ze-core infrastructure layer specs
└── arch/             ← architecture decision records
```

## Writing a new spec

Copy `TEMPLATE.md` into the appropriate subdirectory, fill in the sections, and
remove any sections that don't apply. Required sections: **Purpose**,
**Responsibilities**, **Out of Scope**. All Open Questions must be resolved or
explicitly deferred before implementation begins.

- New **feature or phase** spec → `phases/<next-number>-<name>.md`
- New **ze-core module** spec → `core/<next-number>-<name>.md`
- New **architecture decision** → `arch/<name>.md`

## Phase specs (`phases/`)

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
| 43 | [React Web App](phases/43-react-web-app.md) | 🔄 Planned |
| 44 | [Calendar Package Split](phases/44-package-split-google-calendar-api.md) | ✅ Done |
| 46 | [Accountability Layer](phases/46-accountability-layer.md) | ✅ Done |
| 47 | [Plugin Framework](phases/47-plugin-framework.md) | 🔄 In Progress (tool namespacing deferred) |
| 48 | [Ze Core Split](phases/48-core-split.md) | ✅ Done |
| 49 | [Ze SDK](phases/49-ze-sdk.md) | ✅ Done |
| 50 | [News Preference Model](phases/50-news-preferences.md) | ✅ Done |
| 51 | [Onboarding Platform](phases/51-onboarding.md) | ✅ Done |
| 52 | [Session-Grouped Episode Consolidation](phases/52-session-grouped-consolidation.md) | 🔄 In Progress |
| 53 | [Eval Consolidation](phases/53-eval-consolidation.md) | 🔄 Pending |
| 54 | [Progress Messages](phases/54-progress-messages.md) | ✅ Done |
| 55 | [Signal Substrate](phases/55-signal-substrate.md) | 🔲 Pending (v1) |
| 56 | [Salience & Relevance Model](phases/56-salience-relevance-model.md) | 🔲 Pending (v1) |
| 57 | [Correlation Engine](phases/57-correlation-engine.md) | 🔲 Pending (v1) |
| 58 | [Inline Conversational Correlation](phases/58-inline-correlation.md) | 🔲 Pending (v1 — sole consumer) |
| 59 | [Proactive Correlation Push](phases/59-proactive-correlation-push.md) | 🔲 Deferred (post-v1) |
| 60 | [Cross-Plugin Signal Contract](phases/60-signal-source-contract.md) | 🔲 Pending |
| 61 | [Convergence & Pressure Points](phases/61-convergence-pressure-points.md) | 🔲 Pending (design-only) |
| 62 | [Data Portability](phases/62-data-portability.md) | ✅ Done |
| 63 | [Integration Framework](phases/63-integration-framework.md) | ✅ Done |
| 64 | [Plugin Package Extraction](phases/64-plugin-package-extraction.md) | 🔲 Pending |
| 65 | [Eager Session Summaries](phases/65-eager-session-summaries.md) | 🔲 Pending |
| 66 | [Primitive UI](phases/66-primitive-ui.md) | 🔲 Pending |
| 67 | [Finance Plugin](phases/67-finance-plugin.md) | 🔲 Pending |
| 68 | [ze-data Package](phases/68-ze-data.md) | 🔲 Pending |
| 69 | [ze-ingestion Pipeline](phases/69-ze-ingestion.md) | 🔲 Pending |
| 70 | [Finance Recurring Detection](phases/70-finance-recurring.md) | ✅ Done |
| 71 | [Cross-Goal Awareness](phases/71-cross-goal-awareness.md) | 🔲 Pending |

## Ze Core specs (`core/`)

| # | Spec | Module |
|---|------|--------|
| 01 | [Agent Decorator & BaseAgent](core/01-agent.md) | `ze_core/orchestration/` |
| 02 | [AppInterface](core/02-app-interface.md) | `ze_core/interface/` |
| 03 | [Capability Gate](core/03-capability-gate.md) | `ze_core/capability/` |
| 04 | [Routing](core/04-routing.md) | `ze_core/routing/` |
| 05 | [Orchestration Graph](core/05-orchestration.md) | `ze_core/orchestration/` |
| 06 | [Memory](core/06-memory.md) | `ze_core/memory/` |
| 07 | [Container](core/07-container.md) | `ze_core/container.py` |
| 08 | [Contacts](core/08-contacts.md) | `ze_core/` (contacts primitive) |

## Architecture decisions (`arch/`)

| Spec | Decision |
|------|----------|
| [Package Reorg](arch/package-reorg.md) | Monorepo split: ze-core / ze-personal / ze / ze-browser |
| [Plugin Agents](arch/plugin-agents.md) | ZePlugin ABC, domain agent migration to ze-personal |
| [Memory Package Extraction](arch/memory-package-split.md) | Hard-cut memory into `ze_memory` with module-specific retrieval, explicit task state, and no shim |
| [Memory Graph Augmentation](arch/memory-graph-augmentation.md) | Add bounded, provenance-first relationships and traversal inside `ze_memory` |
| [Correlation Engine](arch/correlation-engine.md) | Bounded relevance-gated correlation over a shared signal/graph substrate; not a world model |
| [Monorepo Layout](arch/monorepo-layout.md) | Dissolve `packages/`; promote `core/`, `plugins/`, `apps/` to repo root |
