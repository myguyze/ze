# core/

Shared infrastructure packages. These packages contain no personal-assistant domain
logic — only the framework primitives that every other package builds on.

**Rule:** a `core/` package may never import from `plugins/` or `apps/`.

Package READMEs follow [docs/package-readme-template.md](../docs/package-readme-template.md).
Tests run from the repo root via `make test-<short-name>`. See [docs/testing.md](../docs/testing.md).

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-agents](ze-agents/) | Developer API — `BaseAgent`, `@agent`, `@tool`, shared types, harness hooks |
| [ze-plugin](ze-plugin/) | Plugin framework — `ZePlugin`, channels, signals, `ZeIntegration` protocol |
| [ze-proactive](ze-proactive/) | Job scheduling — `ProactiveScheduler`, `ProactiveJob`, push log |
| [ze-sdk](ze-sdk/) | Public SDK surface — flat re-export layer for plugin authors |
| [ze-core](ze-core/) | LangGraph orchestration, routing, capability gate, OpenRouter, telemetry |
| [ze-memory](ze-memory/) | Memory persistence and retrieval — facts, episodes, graph, consolidation |
| [ze-correlation](ze-correlation/) | Cross-domain hypothesis formation from the memory graph |
| [ze-browser](ze-browser/) | HTTP client for the Playwright browser sidecar |
| [ze-notifications](ze-notifications/) | Push notification abstraction (ntfy) |
| [ze-components](ze-components/) | Server-driven UI component descriptors for the React web client |
| [ze-onboarding](ze-onboarding/) | Plugin-extensible onboarding coordinator and reset domain types |
| [ze-data](ze-data/) | Data management — `DataDomain` descriptor and `DataPortabilityService` |
| [ze-ingestion](ze-ingestion/) | Content ingestion pipeline — fetch, process, extract, and archive any external content |
| [ze-eval](ze-eval/) | Eval infrastructure — runner, judge, verifier, MCP server |

## Dependency graph

```
ze-onboarding     ←  ze-agents
ze-agents         ←  ze-onboarding
ze-plugin         ←  ze-agents
ze-proactive      ←  ze-agents
ze-memory         ←  ze-agents
ze-correlation    ←  ze-agents, ze-memory
ze-browser        ←  no ze deps
ze-notifications  ←  no ze deps
ze-components     ←  no ze deps
ze-eval           ←  no ze deps
ze-data           ←  no ze deps
ze-ingestion      ←  ze-agents, ze-memory, ze-browser
ze-sdk            ←  ze-agents, ze-data, ze-plugin, ze-proactive, ze-memory, ze-onboarding
ze-core           ←  ze-agents, ze-plugin
```

## Where new code goes

| New code | Package |
|----------|---------|
| New agent execution primitive (`BaseAgent` hook, `@tool` behaviour) | `ze-agents` |
| New plugin seam (`ZePlugin` hook, channel type, signal contract) | `ze-plugin` |
| New infrastructure primitive (router, gate, graph node) | `ze-core` |
| New memory retrieval policy, graph predicate, or consolidation strategy | `ze-memory` |
| New cross-domain correlation logic | `ze-correlation` |
| New push notification backend | `ze-notifications` |
| New server-driven UI component type | `ze-components` |
| New setup-flow primitive or onboarding provider contract | `ze-onboarding` |
| New browser sidecar endpoint client | `ze-browser` |
| New eval runner, judge, or verifier | `ze-eval` |

If the code has any dependency on personal-assistant domain concepts (goals,
workflows, contacts, persona), it does not belong here.

## Signal pipeline

Cross-domain correlation is fed by plugin-emitted signals:

```
plugins (SignalSource)  →  ze-api (collect + dedupe)  →  ze-memory (admission + ingest)
                                                              ↓
                                                         ze-correlation (hypotheses)
```

Implement `SignalSource` in plugins that produce time-stamped domain events worth correlating. See `specs/phases/060-signal-source-contract/spec.md`.
