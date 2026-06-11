# core/

Shared infrastructure packages. These packages contain no personal-assistant domain
logic — only the framework primitives that every other package builds on.

**Rule:** a `core/` package may never import from `plugins/` or `apps/`.

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-core](ze-core/) | LangGraph orchestration, routing, capability gate, OpenRouter client, telemetry, `ZePlugin` ABC |
| [ze-memory](ze-memory/) | Memory persistence and retrieval — facts, episodes, graph, consolidation |
| [ze-browser](ze-browser/) | HTTP client for the Playwright browser sidecar |
| [ze-google](ze-google/) | Google OAuth2 credentials and service client factories (no Ze deps) |
| [ze-notifications](ze-notifications/) | Push notification abstraction (ntfy) |
| [ze-components](ze-components/) | Server-driven UI component descriptors sent to the Flutter app |
| [ze-onboarding](ze-onboarding/) | Plugin-extensible onboarding coordinator, provider contracts, reset domain types |

## Dependency graph

```
ze-google         ←  no ze deps
ze-notifications  ←  no ze deps
ze-onboarding     ←  no ze deps
ze-core           ←  ze-agents
ze-memory         ←  ze-agents
ze-browser        ←  no ze deps
ze-components     ←  ze-agents
```

## Where new code goes

| New code | Package |
|----------|---------|
| New infrastructure primitive (router, gate, store type) | `ze-core` |
| New memory retrieval policy, graph predicate, or consolidation strategy | `ze-memory` |
| New push notification backend | `ze-notifications` |
| New server-driven UI component type | `ze-components` |
| New setup-flow primitive, onboarding step/seed type, provider contract | `ze-onboarding` |
| New Google service client factory | `ze-google` |
| New browser sidecar endpoint | `ze-browser` |

If the code has any dependency on personal-assistant domain concepts (goals,
workflows, contacts, persona), it does not belong here.
