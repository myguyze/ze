<div align="center">

# Ze

**Jarvis. Make no mistakes.**

A self-hosted personal AI assistant. Single-user, spec-first, somewhere in the middle of becoming something genuinely useful.

<p>
  <a href="https://github.com/joaoajmatos/ze/actions/workflows/ci.yml"><img src="https://github.com/joaoajmatos/ze/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/interface-React-61DAFB.svg" alt="React">
  <img src="https://img.shields.io/badge/LLM-OpenRouter-000000.svg" alt="OpenRouter">
  <img src="https://img.shields.io/badge/license-Unlicense-green.svg" alt="Unlicense">
</p>

</div>

---

## What this is

An honest attempt at building a personal AI that does more than answer questions.

The objective: an assistant that holds context across weeks, works in the background, and connects things that happen in separate parts of your life — calendar, email, news, long-running projects. Not a chat window that resets. Something closer to Jarvis. That's the whole brief.

It isn't there yet. But 60+ shipped phases in, the infrastructure is real and it's getting closer.

---

## Where it is now

Python/FastAPI backend, LangGraph orchestration, React web client, plugin-per-domain architecture. Routing uses local embeddings — zero LLM calls until an agent actually needs to act. All LLM traffic goes through OpenRouter. Graph state is checkpointed in Postgres and survives restarts.

### Goal engine

The center of gravity. Hand Ze an objective and it decomposes into milestones, dispatches them to specialist agents on a schedule, pauses at verification gates with a progress narrative, replans on failure, and writes a retrospective when it finishes. Steer mid-flight by talking — no slash commands. Background sweep runs every 15 minutes regardless of whether you're online.

This is the bet. Everything else compounds on top of it.

### Memory

Facts and episodes extracted after each turn, consolidated nightly, profile synthesised weekly. Goal learnings promoted to long-term memory on completion. `pgvector` for retrieval.

### How Ze gets sharper

Memory isn't a single inflow. Everything feeds the same substrate:

```
conversation turns   →  facts + episodes  ─┐
ingested content     →  extracted facts   ──┤
                                            ├→  memory graph  →  retrieval  →  every agent turn
domain events        →  signals           ──┤
(calendar, news, …)      ↓                  │
                     admission gate  ────────┘
                          ↓
                    correlation engine  →  push when salience is high
```

Conversations write what Ze learns from talking. Ingestion (`ze-ingestion`) feeds knowledge from any URL, PDF, YouTube video, or file — extracted facts land in the same store. Domain plugins emit `SignalSource` events that are scored for relevance, written to the memory graph, and fed into the correlation engine. Goals promote learnings on completion. Every inflow compounds.

The design intent is that Ze gets sharper without being explicitly fed. Drop a PDF in. Share a video. The facts join everything else Ze already knows.

Every domain plugin also declares a `DataDomain` — an export, import, and delete contract. The portability service honours it. You own the data at every layer.

### Proactive surface

Ze doesn't wait to be asked. Morning briefings, calendar reminders, weekly insights, goal suggestions, stuck-goal alerts, news fetch — all background jobs, configurable in `config.yaml`.

### Agents

Research, companion, calendar, email, reminders, workflow, goals, prospecting, news, ingestion. Each runs in a ReAct loop via `BaseAgent`; tool access is gated per-agent.

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
| `ingestion` | URL / PDF / video / audio / text → memory | Autonomous |

</details>

### Plugin extension surface

`ZePlugin` is the seam. A domain package hooks in by declaring what it contributes:

| Hook | What it provides |
|---|---|
| `agents()` | Agents registered into the routing graph |
| `ingestion_extractors()` | Domain-specific extractors (e.g. `TransactionExtractor` for PDFs) |
| `ingestion_fetchers()` | Custom content fetchers (e.g. Notion, proprietary APIs) |
| `signal_sources()` | Domain events fed into the correlation pipeline |
| `data_domains()` | Export / import / delete contract for every table the plugin owns |
| `memory_policies()` | Per-agent retrieval strategy from the memory graph |
| `channels()` | Outbound communication channels (email, etc.) |

The hooks compose. A finance plugin registers a `TransactionExtractor` so that ingesting a bank statement produces structured transaction facts — which land in memory, which surface in retrieval, which the correlation engine can cross with calendar and news. That chain is the whole point.

---

## Where it's going

The goal engine needs to carry a full personal project across weeks with minimal intervention — research, plan, execute, verify, iterate, report. That's the target.

Near-term: finance and legal plugins, richer correlation reasoning, deeper signal coverage.

---

## How a message flows

Every turn runs through a LangGraph graph checkpointed in Postgres.

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
core/           ze-core · ze-agents · ze-plugin · ze-sdk · ze-memory · ze-correlation
                ze-data · ze-ingestion · ze-browser · ze-notifications · …
integrations/   ze-google · ze-yt · …
specs/          one spec per phase, written before the code
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

Every package has a README. Conventions: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Documentation

| Doc | Topic |
|---|---|
| [architecture.md](docs/architecture.md) | System design, graph flow |
| [package-architecture.md](docs/package-architecture.md) | Monorepo, `ZePlugin`, dependency rules |
| [extending-ze.md](docs/extending-ze.md) | Agents, plugins, jobs, channels |
| [ingestion.md](docs/ingestion.md) | Ingestion pipeline — fetchers, processors, extractors, plugin hooks |
| [memory.md](docs/memory.md) | Facts, episodes, graph, retrieval policies |
| [goals.md](docs/goals.md) | Goal engine |
| [sdk.md](docs/sdk.md) | `ze_sdk` reference |
| [data-portability.md](docs/data-portability.md) | Export, import, and deletion — `DataDomain` contract |
| [specs/](specs/) | Design specs — where Ze is going next |

Deploy: [docs/deployment.md](docs/deployment.md)

---

## Security

Single-user by design. Strong `ZE_API_KEY`, secrets out of git, non-guessable ntfy topic. Don't expose as a shared service without hardening.

---

## License

[The Unlicense](UNLICENSE) — public domain. Take it anywhere, zero conditions.
