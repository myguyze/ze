# Ze — Documentation

| Doc | What it covers |
|-----|----------------|
| [architecture.md](architecture.md) | System overview, graph flow, all modules at a glance |
| [package-architecture.md](package-architecture.md) | Monorepo split (ze-core / ze-personal / ze / ze-browser), ZePlugin extension point, where new code belongs |
| [adding-an-agent.md](adding-an-agent.md) | Step-by-step guide for authoring a new agent |
| [configuration.md](configuration.md) | All config keys — `.env`, `config.yaml`, `persona.yaml` |
| [memory.md](memory.md) | Facts, episodes, profile synthesis, nightly consolidation, inspection endpoints |
| [scheduled-jobs.md](scheduled-jobs.md) | Background job schedule, memory lifecycle, proactive push pipeline |
| [goals.md](goals.md) | Goal Engine — conversational usage, milestone execution, verification gates |
| [workflows.md](workflows.md) | Workflow agent — multi-step plans, scheduling, step execution |
| [news.md](news.md) | News package — RSS ingestion, personalised ranking, credibility analysis |
| [channels.md](channels.md) | Adding a new outbound communication channel (LinkedIn, WhatsApp, etc.) |
| [deployment.md](deployment.md) | Fly.io deployment, GitHub Actions CI, environment setup |
| [eval.md](eval.md) | End-to-end eval system via MCP — running evals, LLM-as-judge |
