# Ze — Documentation

| Doc | What it covers |
|-----|----------------|
| [architecture.md](architecture.md) | System overview, graph flow, all modules at a glance |
| [package-architecture.md](package-architecture.md) | Monorepo split (13 packages), ZePlugin extension point, where new code belongs |
| [sdk.md](sdk.md) | SDK reference — all `ze_sdk` exports, BaseAgent API, @agent/@tool decorators, ZePlugin hooks |
| [extending-ze.md](extending-ze.md) | End-to-end guide — adding agents, creating new plugins, proactive jobs, channels |
| [native-interface.md](native-interface.md) | WebSocket protocol, frame types, confirmation flow, ntfy push, unread replay |
| [onboarding.md](onboarding.md) | Plugin-extensible onboarding, setup forms, seed review, and reset scopes |
| [adding-an-agent.md](adding-an-agent.md) | Step-by-step guide for authoring a new agent |
| [configuration.md](configuration.md) | All config keys — `.env`, `config.yaml`, `persona.yaml` |
| [memory.md](memory.md) | ze-memory package — facts, episodes, events, procedures, profile facets, graph layer, retrieval policies |
| [scheduled-jobs.md](scheduled-jobs.md) | Background job schedule, memory lifecycle, proactive push pipeline |
| [goals.md](goals.md) | Goal Engine — conversational usage, milestone execution, verification gates |
| [workflows.md](workflows.md) | Workflow agent — multi-step plans, scheduling, step execution |
| [news.md](news.md) | News package — RSS ingestion, personalised ranking, credibility analysis |
| [channels.md](channels.md) | Adding a new outbound communication channel (LinkedIn, WhatsApp, etc.) |
| [deployment.md](deployment.md) | Fly.io deployment, GitHub Actions CI, environment setup |
| [eval.md](eval.md) | End-to-end eval system via MCP — running evals, LLM-as-judge |
