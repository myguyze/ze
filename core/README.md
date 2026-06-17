# core/

Shared infrastructure packages. These packages contain no personal-assistant domain
logic — only the framework primitives that every other package builds on.

**Rule:** a `core/` package may never import from `plugins/` or `apps/`.

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-agents](ze-agents/) | Developer API — `BaseAgent`, `@agent`, `@tool`, `ZePlugin`, shared types |
| [ze-proactive](ze-proactive/) | Job scheduling framework — `ProactiveScheduler`, `ProactiveJob` |
| [ze-sdk](ze-sdk/) | Public SDK surface — flat re-export layer for plugin authors |
| [ze-core](ze-core/) | LangGraph orchestration, routing, capability gate, OpenRouter client, telemetry |
| [ze-memory](ze-memory/) | Memory persistence and retrieval — facts, episodes, graph, consolidation |
| [ze-browser](ze-browser/) | HTTP client for the Playwright browser sidecar |
| [ze-notifications](ze-notifications/) | Push notification abstraction (ntfy) |
| [ze-components](ze-components/) | Server-driven UI component descriptors sent to the React web client |
| [ze-onboarding](ze-onboarding/) | Plugin-extensible onboarding coordinator, provider contracts, reset domain types |

## Dependency graph

```
ze-notifications  ←  no ze deps
ze-onboarding     ←  no ze deps
ze-agents         ←  ze-onboarding
ze-proactive      ←  ze-agents
ze-memory         ←  ze-agents
ze-browser        ←  no ze deps
ze-components     ←  ze-agents
ze-sdk            ←  ze-agents, ze-proactive, ze-memory, ze-onboarding
ze-core           ←  ze-agents
```

## Where new code goes

| New code | Package |
|----------|---------|
| New infrastructure primitive (router, gate, store type) | `ze-core` |
| New memory retrieval policy, graph predicate, or consolidation strategy | `ze-memory` |
| New push notification backend | `ze-notifications` |
| New server-driven UI component type | `ze-components` |
| New setup-flow primitive, onboarding step/seed type, provider contract | `ze-onboarding` |
| New browser sidecar endpoint | `ze-browser` |

If the code has any dependency on personal-assistant domain concepts (goals,
workflows, contacts, persona), it does not belong here.
