<div align="center">

# Ze

**Jarvis. Make no mistakes.**

A self-hosted personal AI **platform** that works across weeks, connects everything it knows, and keeps getting sharper — not a chat window that resets when you close the tab.

<p>
  <a href="https://github.com/joaoajmatos/ze/actions/workflows/ci.yml"><img src="https://github.com/joaoajmatos/ze/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/interface-React-61DAFB.svg" alt="React">
  <img src="https://img.shields.io/badge/LLM-OpenRouter-000000.svg" alt="OpenRouter">
  <img src="https://img.shields.io/badge/license-Unlicense-green.svg" alt="Unlicense">
</p>

</div>

---

## The vision

> I want to make Jarvis, make no mistakes.

That's the whole brief. Everything else is engineering.

In 2026, memory and confirmations are table stakes. Ze is built for what comes after: **standing work** — objectives that run for weeks, background jobs that compound, domains that talk to each other, and a codebase designed to keep evolving without collapsing into a monolith.

Single-user. Self-hosted. Yours entirely.

---

## What makes Ze different

Most AI apps optimise for the next reply. Ze optimises for the **next month**.

| | Typical AI app | Ze |
|---|---|---|
| **Horizon** | This conversation | Multi-week goals with milestones, replanning, retrospectives |
| **Operation** | You drive every turn | A background fleet — briefings, goal sweeps, news fetch, correlation runs |
| **Intelligence** | Retrieval over a flat memory | Memory **graph** + cross-domain **correlation** (news × calendar × goals) |
| **Shape** | Product you configure | **Platform** you extend — plugins, channels, signals, server-driven UI |
| **Evolution** | Wait for the vendor | Spec-first monorepo, 60+ shipped phases, public domain — fork it, extend it |

Ze doesn't wait to be asked. It researches, plans, executes, consolidates what it learned overnight, and reaches out when something actually matters.

---

## Three things worth building on

### 1. Work that outlasts the session

The goal engine is the centre of gravity. Hand Ze an objective and it decomposes into milestones, dispatches them to specialist agents on a schedule, pauses at verification gates with a progress narrative, replans when things fail, and pushes a real retrospective when it's done. Steer mid-flight by talking — no slash commands.

Graph state is checkpointed in Postgres. Confirmations and in-progress goals survive restarts. A sweep advances active goals every 15 minutes whether you're online or not.

### 2. A mind that connects domains

Facts and episodes are the foundation. On top of that, Ze builds something rarer: **cross-plugin signals** ingested into a memory graph, scored by a relevance gate, and reasoned over by a correlation engine.

A calendar event, a news headline, and an active goal aren't three separate features — they're inputs to the same substrate. Ze can surface "this article relates to the milestone you're stuck on" and push it proactively when salience is high.

```
plugins (SignalSource)  →  admission gate  →  memory graph  →  correlation engine  →  push
```

News and calendar emit signals today. Finance and legal plugins are next. The pipeline is the product.

### 3. A platform that keeps growing

Ze isn't a single app with feature flags — it's **20+ packages** with a strict dependency graph, a plugin SDK, and spec-first development (`specs/phases/`). Domain logic lives in plugins; the engine handles routing, orchestration, memory, correlation, and delivery.

| Extension | Add |
|---|---|
| `ZePlugin` | Agents, graph nodes, jobs, memory policies, migrations |
| `SignalSource` | Domain events for correlation |
| `Channel` | Outbound comms (Gmail today; more tomorrow) |
| `@agent` / `@tool` | Capabilities with local embedding routing |
| Server-driven UI | Components in chat without a frontend deploy |

Plugins self-register via entry points. The bootstrapper sorts dependencies, merges graph contributions, collects signal sources. You extend Ze; you don't patch the engine.

See [docs/package-architecture.md](docs/package-architecture.md) · [docs/extending-ze.md](docs/extending-ze.md)

---

## The stack (today)

**Agents** — research, companion, calendar, email, reminders, workflow, goals, prospecting, news. Local embeddings route before any LLM call.

**Proactive surface** — morning briefings, calendar reminders, weekly insights, goal narratives and suggestions, news fetch, cost reconciliation, stuck-goal alerts. Configurable in `config.yaml`.

**Memory lifecycle** — extraction after each turn, nightly consolidation, profile synthesis, weekly insight generation. Goal learnings promoted to long-term memory on completion.

**Platform plumbing** — LangGraph orchestration, capability modes, cost telemetry, eval suite with MCP server, multimodal input, persona dials, contact extraction, browser sidecar for autonomous research.

Trust mechanics (approved facts, confirmation flows, per-action capability modes) are built in — they're the floor, not the ceiling.

<details>
<summary>Agent reference</summary>

| Agent | Domain | Default posture |
|---|---|---|
| `research` | Web search + synthesis, delegation | Autonomous |
| `companion` | Reasoning, writing, conversation | Autonomous |
| `calendar` | Google Calendar CRUD + availability | Read auto · writes confirm |
| `email` | Gmail list / read / draft / send | Read auto · draft-first |
| `reminders` | NL reminders + proactive push | Autonomous |
| `workflow` | Recurring multi-step tasks | Read auto · manage confirm |
| `goals` | Multi-week autonomous objectives | Read auto · writes confirm |
| `prospecting` | Browser-sidecar research + outreach | Autonomous |
| `news` | Personalised RSS headlines + search | Autonomous |

</details>

---

## How a message flows

Every turn runs through a LangGraph checkpointed in Postgres. Routing uses local embeddings — zero LLM calls until an agent actually needs to act.

```mermaid
flowchart TD
    A([ze-web]) -->|WebSocket /ws| PRE[preprocess]
    PRE --> ER[embed_route]
    ER --> FC[fetch_context]
    FC --> CG[capability_check]
    CG -->|EXECUTE| EX[agent.run]
    CG -->|CONFIRM| AC[await_confirmation]
    EX --> WM[write_memory]
    WM --> R([response + components])
```

Full diagram: [docs/architecture.md](docs/architecture.md)

---

## Monorepo

```
apps/           ze-api · ze-web
plugins/        personal · email · calendar · news · prospecting · finance* · legal*
core/           ze-core · ze-agents · ze-plugin · ze-sdk · ze-memory · ze-correlation · …
integrations/   ze-google · …
specs/          spec-first design — continuous development, one phase at a time
```

| Layer | Tech |
|---|---|
| Runtime | Python 3.12 · FastAPI · LangGraph · AsyncPostgresSaver |
| Client | React · Vite · TypeScript · Tailwind |
| LLM | OpenRouter · local embeddings (multilingual MiniLM) |
| Data | PostgreSQL 16 + pgvector |
| Push | ntfy · WebSocket `/ws` |

---

## Quick start

**Prerequisites:** Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker, [OpenRouter](https://openrouter.ai) key, ntfy for push.

```bash
git clone https://github.com/joaoajmatos/ze.git && cd ze
make install

cp apps/ze-api/.env.example apps/ze-api/.env
make db-up && make migrate
make dev-full    # backend :8000 + web :5173
```

Google Calendar + Gmail: `make google-auth` · Config: [docs/configuration.md](docs/configuration.md)

---

## Development

```bash
make test              # ze-api (fast)
make test-<name>       # any package — docs/testing.md
make test-all          # full suite
make eval              # agent evals (make dev-eval first)
```

60+ phases shipped. Every package has a README. Conventions: [CONTRIBUTING.md](CONTRIBUTING.md) · Roadmap ideas: [docs/roadmap-brainstorm.md](docs/roadmap-brainstorm.md)

---

## Documentation

| Doc | Topic |
|---|---|
| [architecture.md](docs/architecture.md) | System design, graph flow |
| [package-architecture.md](docs/package-architecture.md) | Monorepo, `ZePlugin`, dependency rules |
| [extending-ze.md](docs/extending-ze.md) | Agents, plugins, jobs, channels |
| [goals.md](docs/goals.md) | Goal engine |
| [memory.md](docs/memory.md) | Facts, episodes, graph |
| [sdk.md](docs/sdk.md) | `ze_sdk` reference |
| [specs/](specs/) | Design specs — where Ze is going next |
| [VISION.md](VISION.md) | One sentence |

Deploy: [docs/deployment.md](docs/deployment.md)

---

## Security

Single-user by design. Strong `ZE_API_KEY`, secrets out of git, non-guessable ntfy topic. Don't expose as a shared service without hardening.

---

## License

[The Unlicense](UNLICENSE) — public domain.

Ze is built to compound: specs, plugins, signals, goals that run for weeks. The license says take it anywhere — zero conditions, dedicated to the public domain *"to the detriment of our heirs and successors."*

Make no mistakes in the architecture. Make whatever you want with the code.
