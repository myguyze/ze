# Ze Core — Vision Document

> A runtime for persistent, single-user AI applications.

---

## The Problem

Building a personal AI application today means making the same decisions every time:
how to route messages to the right agent, how to gate risky actions behind user
approval, how to persist memory across sessions, how to push proactive notifications
without being asked, how to track what the LLM is costing you. None of this is hard
in isolation. But wiring it all together — correctly, coherently, and in a way that
survives restarts, handles failures, and stays maintainable — takes weeks of work
before you write a single line of application logic.

Existing frameworks stop at the agent loop. LangChain gives you chains and tools.
CrewAI gives you multi-agent coordination. What nobody gives you is the full vertical:
an application that persists, remembers, acts on schedules, and integrates with your
actual life — ready to deploy in a weekend.

Ze Core is that vertical, extracted.

---

## What Ze Core Is

Ze Core is a Python framework for building **persistent, single-user AI applications**.
It encodes the architectural decisions that are the same across every application of
this type, so you stop making them and start building.

The mental model is Ruby on Rails, applied to AI applications. Rails encoded one
pattern — MVC, REST, relational database — so well that an entire class of web
applications became trivially fast to build. It also made a second, equally important
decision: configuration is for what genuinely varies between deployments. Everything
else is a convention. Database port? Convention. Table naming? Convention. You only
write config for what you actually need to change.

Ze Core applies the same discipline. Routing thresholds, memory consolidation
parameters, embedding model selection — these are implementation details that should
have sensible defaults in code. An application author writes agents, an interface
adapter, and a config file of roughly thirty lines. The framework handles everything
else.

Ze Core is not a general agent framework. It does not try to cover every AI use case.
It covers one specific, underserved class extremely well: personal assistants, research
companions, life automation tools — applications that have an **ongoing relationship
with one user over time**.

---

## Origin

Ze Core is extracted from Ze — a production personal assistant with the following
capabilities, all battle-tested and running:

- Multi-agent routing using local embeddings with LLM fallback for ambiguous requests
- Capability gates — per-intent permission modes with inline confirmation flows
- Semantic memory — facts, episodes, nightly consolidation, synthesised user profile
- Goal engine — multi-week objectives with milestones and verification gates
- Workflow engine — scheduled and on-demand multi-step task execution
- Proactive behaviors — morning briefings, calendar reminders, weekly insights
- Cost telemetry — per-flow token usage and nightly reconciliation
- Multi-channel output — transport-agnostic message delivery
- Persona system — named profiles with continuous personality dials

The framework is not designed in the abstract. Every primitive exists because a real
application needed it. Ze continues to run on Ze Core after extraction, which means
the abstractions are proven against a real workload.

Ze's current architecture is the starting point, not the target. Several things that
the framework encodes as conventions are today spread across Ze's `config.yaml` —
agent descriptions, capability modes, routing thresholds, memory consolidation
parameters. The extraction reorganises these into the right places: code for decisions
that belong in code, config for decisions that genuinely vary per deployment.

---

## Core Philosophy

**Convention over configuration.** The decisions that are the same across every
persistent AI application are encoded as conventions. Routing thresholds, memory
consolidation parameters, deduplication logic, episode archival schedules — these are
not configuration. They are the framework. You configure secrets, model preferences,
scheduling times, and persona. Nothing else requires a config file.

**Agents are self-describing.** An agent's routing description, capability modes, model
selection, and tool list live in the agent class itself — not in a separate YAML file.
An agent is a single Python file. Reading it tells you everything about what it does,
what it costs, and what permissions it requires. There is no capability YAML to hunt
down, no per-agent config file to keep in sync. This is achieved through the `@agent`
decorator, the central mechanism of Ze Core.

**Explicit trust boundaries.** Every action an agent takes has an explicit permission
mode, declared in the agent class. Nothing executes autonomously unless the developer
has opted in. The capability gate is a first-class citizen, not middleware bolted on
after the fact.

**Memory is an editorial problem.** Agents propose facts. Users approve them.
The application never silently writes to long-term memory. This is a design philosophy,
not a feature flag.

**The full stack, not just the loop.** A running AI application needs routing,
gating, memory, scheduling, interfaces, cost tracking, and observability. Ze Core
provides all of it. You provide the agents and the integrations.

**Zero LLM calls in the routing happy path.** Local embeddings handle the common
case. The LLM is a fallback for ambiguity, not the default path for every message.

**Dependency injection throughout.** Every module accepts its dependencies as
constructor arguments. Nothing reads from globals. This makes testing straightforward
and makes the framework genuinely composable.

---

## Configuration Philosophy

Ze Core takes an explicit position on configuration: **configuration is for secrets,
scheduling preferences, and model selection. Everything else is a convention.**

This position is derived directly from Ze's config file, which after analysis contains
three categories of settings:

### Category 1 — Eliminated (encoded as framework conventions)

These values are the same across every application of this type. They have no business
being in a config file. In Ze's current `config.yaml` they occupy significant space;
in Ze Core they become named defaults in code:

- Routing thresholds and embedding model selection
- Memory consolidation parameters (merge thresholds, TTLs, archive batch sizes)
- Profile synthesis minimums
- Episode recency windows

These become sensible defaults in code. Override them in Python if you have a specific
reason. You will rarely have one.

### Category 2 — Moved into the agent definition

Per-agent configuration — model, timeout, capability modes, vision capability, tools,
routing description — lives in the agent class itself. In Ze today, this information is
split across two places: a YAML block in `config.yaml` and the agent's Python file. Ze
Core collapses this into one.

The mechanism is the `@agent` decorator. When applied to a class, it registers the
class in the agent registry and makes its class attributes available to the framework.
The routing engine reads `description` at startup to build its embedding matrix. The
capability gate reads `capabilities` instead of a YAML file. The execution node reads
`vision_capable` and `timeout` from the class. No other file, no separate YAML block.

**Convention-based discovery.** Agents live in the `agents/` directory by convention.
Ze Core scans this directory at startup, imports every `agent.py` it finds, and the
`@agent` decorator handles registration when each module is imported. You never write
a list of agents. You never register them manually. You put a file in the right place
and it works — the same way Rails finds controllers in `app/controllers/`.

Setting `enabled = False` on an agent class excludes it from routing and prevents
instantiation. The `@agent` decorator still fires at import time, but the framework
skips the agent during startup — it does not appear in the embedding matrix and
cannot be reached by any message.

```python
@agent
class CalendarAgent(BaseAgent):
    model = "anthropic/claude-haiku-4-5"
    model_simple = None          # already cheapest tier — no fallback
    vision_capable = True
    timeout = 30
    enabled = True
    description = """
        Manages Google Calendar events. Use for creating, reading, updating,
        or deleting events, checking availability, or finding free time.
    """
    capabilities = {
        "read":   Mode.AUTONOMOUS,
        "create": Mode.CONFIRM,
        "update": Mode.CONFIRM,
        "delete": Mode.CONFIRM,
    }
    intent_map = {
        "read":   "Search and retrieve calendar events.",
        "create": "Create a new calendar event.",
        "update": "Modify an existing calendar event.",
        "delete": "Remove a calendar event.",
    }
    tools = [list_events, create_event, update_event, delete_event]

    system_prompt = """..."""
```

Reading this file tells you everything: what the agent does, how it is routed, what
it costs, and what permissions it requires. No YAML hunting. No config file to keep in
sync. Changing a capability mode is a code change, visible in code review.

### Category 3 — Kept (genuine per-deployment variation)

These genuinely vary between deployments and users. They belong in config:

```yaml
# .env — secrets, never committed
OPENROUTER_API_KEY=...
DATABASE_URL=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_ID=...
GOOGLE_CLIENT_ID=...            # optional, only if using Google integrations
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...

# config.yaml — behavioural preferences (~30 lines)
models:
  router:     anthropic/claude-haiku-4-5    # model for ambiguous routing fallback
  synthesis:  anthropic/claude-haiku-4-5    # model for multi-agent response merging

persona:
  profile: default                           # starting profile name

proactive:
  briefing:
    cron: "0 8 * * *"                        # when YOU want your morning briefing
  insights:
    cron: "0 7 * * 0"                        # when YOU want weekly insights
```

That is the entire config file. Thirty lines. The rest is the framework.

### Persona profiles are content, not configuration

Persona profiles are a special case. They are the application author's creative
choices about voice and personality — not deployment parameters. In Ze today they
live inline in `config.yaml` alongside routing and memory settings. In Ze Core they
move to a dedicated `persona.yaml` file that the framework provides a working default
for out of the box. Authors who want to customise create their own. Authors who don't
get a sensible default persona without touching a config file.

### Application-specific config stays in the application

Settings specific to Ze — prospecting parameters, browser service URLs, contacts
consolidation schedules — are not framework concerns. They live in Ze's own config,
not in Ze Core. The framework has no opinion about these.

---

## The Primitives

Ze Core is built around six primitives. Together they cover the full lifecycle of a
persistent AI application.

### 1. Routing

The routing primitive takes an incoming message and decides which agent handles it,
without involving an LLM in the common case.

At startup, each registered agent's `description` string is embedded using a shared
local embedding model (default: `paraphrase-multilingual-MiniLM-L12-v2`, loaded once, never reconfigured).
When a message arrives, it is embedded and scored against all agent embeddings by
cosine similarity.

Three outcomes are possible:

- **Confident single match** — route directly, no LLM involved.
- **Ambiguous** (two agents nearly tied) — a small LLM decomposes the request
  into subtasks, each routed independently.
- **Low confidence** — LLM fallback classifies the intent.

A complexity classifier runs in-process alongside routing. It uses heuristic signals
— word count, question marks, conjunctions — to assign requests to `simple` or
`full` model tiers. No extra LLM call. No added latency. Agents that declare a
`model_simple` field receive the cheaper model automatically for simple requests.

Every routing decision is logged with scores and outcome for observability.

The routing thresholds (`0.55` confidence, `0.10` gap) are framework defaults.
They are not in the config file. Override them in code only if you have measured
a reason to.

### 2. Capability Gate

Every agent action has an explicit permission mode, declared in the agent class.
The gate is evaluated before execution on every request.

| Mode | Behaviour |
|---|---|
| `autonomous` | Execute immediately |
| `confirm` | Pause execution, send a confirmation request to the user. Resume on approval. |
| `draft_only` | Generate a response, never execute |
| `disabled` | Block and return an error message |

Confirmation is handled through the Interface abstraction, so the gate is
transport-agnostic. The confirmation flow — pause, send, await, resume — is
implemented once in the framework. Applications never reimplement it.

Permission modes are declared per intent in the agent class. They are source code,
not runtime configuration. Changing them requires a code change and a redeploy.
Per-session temporary overrides are possible via the `session_overrides` mechanism
in `AgentState`, but they do not survive process restarts.

### 3. Memory

Memory is a two-layer store backed by a vector database, with an editorial model
that keeps the user in control.

**Facts** are short declarative statements extracted from conversations. Agents
propose facts after each run. The framework sends the proposal to the user through
the active interface. Only approved facts are written to long-term storage. Facts
are never written silently.

**Episodes** are automatic summaries of conversation turns. They are written after
every run without user approval.

At each graph invocation, the memory primitive performs a semantic search over both
layers and injects the top-k results into the agent's context. The synthesised user
profile is also injected into every system prompt automatically. Agents never query
memory themselves.

A nightly consolidation pipeline runs on the framework's default schedule (2 AM UTC,
overridable):

1. **Deduplication** — near-duplicate facts are merged. High-similarity pairs are
   merged silently; moderate-similarity pairs are merged by a small LLM. Thresholds
   are framework defaults, not config values.
2. **Expiry** — stale and contradicted facts are expired or archived on framework
   defaults. Reviewed facts are never auto-expired.
3. **Episode archival** — old episodes are summarised in batches and archived.
4. **Profile synthesis** — a structured user portrait is synthesised from all
   reviewed facts and recent episodes. It covers preferences, habits, recurring
   topics, relationships, and goals. Injected into every agent's system prompt.

### 4. Goals

The goals primitive addresses multi-week objectives that don't fit a single workflow
execution. A goal spans days or weeks; a workflow step is what happens inside a
single milestone.

The core types are:

- **Goal** — stated objective, success condition, time horizon.
- **Milestone** — an ordered unit of work, executed by a registered agent.
- **Verification Gate** — a pause point between milestone batches. The user sees
  what was completed, what is planned next, and chooses to proceed, stop, or
  redirect with new instructions.
- **Learning** — an insight captured at each milestone boundary.

The advance loop runs on a schedule (every 15 minutes by default). For each active
goal, it either fires the next milestone through the normal agent registry or fires
a verification gate and waits for user response. Goals in any paused or awaiting
state are skipped until the user responds.

Redirect gates allow free-text instructions that cause the remaining milestone plan
to be regenerated before execution continues.

### 5. Proactive

The proactive primitive gives the application a voice the user didn't ask for.
Scheduled and event-driven pushes are first-class citizens, not background jobs
bolted on separately.

The primitive provides:

- A scheduler backed by a persistent job store (survives restarts)
- Push delivery through the active interface
- A registry of push types: briefings, alerts, reminders, insights
- Cron expressions configurable in `config.yaml`

The framework ships with a default proactive schedule. The application author
configures the timing in `config.yaml`. The jobs themselves are defined in code,
not config.

### 6. Telemetry

The telemetry primitive tracks cost throughout the application automatically.
Attribution context propagates through the async call chain via a Python `ContextVar`,
set once at the flow entry point and read automatically inside the tracker.

Every LLM completion records: agent, flow type, model, input tokens, output tokens,
estimated cost. A nightly reconciler pulls actual billed costs from the provider API
and reconciles them against estimates.

Cost data is queryable by agent, flow type, model, and session. Applications expose
this through whatever interface makes sense for their users.

---

## The Two Critical Abstractions

Two abstractions that do not exist explicitly in Ze must be made explicit in Ze Core
for the framework to be genuinely reusable.

### Store Interface

Ze's memory, goals, and workflows all talk to Postgres and pgvector directly. Ze Core
defines abstract store interfaces — `MemoryStore`, `GoalStore`, `WorkflowStore` — and
ships a Postgres + pgvector implementation as the default.

An application that wants to use SQLite and a local vector index can implement the
same interfaces. The framework does not require Postgres; Ze does.

```python
class MemoryStore(Protocol):
    async def search_facts(self, query_embedding, top_k: int) -> list[Fact]: ...
    async def propose_fact(self, content: str, embedding) -> Fact: ...
    async def approve_fact(self, fact_id: UUID) -> None: ...
    async def get_profile(self) -> UserProfile | None: ...
```

### Interface Abstraction

Ze's interface is Telegram — `chat_id` as identity, inline keyboards for confirmations,
`ForceReply` for edits. This is woven into Ze's confirmation flow and goal gate
handling in ways that need to be cleanly separated.

Ze Core defines an `AppInterface` abstraction with four responsibilities:

```python
class AppInterface(Protocol):
    async def receive(self) -> Message: ...
    async def send(self, message: OutboundMessage) -> None: ...
    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse: ...
    async def push(self, notification: Notification) -> None: ...
```

Ze implements this with Telegram. Another application could implement it with a
web API, Slack, or a CLI. The capability gate and goal verification gates use only
this interface — they never reference Telegram directly.

This seam is the trickiest part of the extraction. The `confirm()` method in
particular is not a conventional request-response. The caller (the capability gate,
inside a LangGraph node) must suspend until the user responds — which may arrive
seconds or minutes later via a completely separate HTTP request. In Ze, a graph is
interrupted at a LangGraph checkpoint and resumed via `graph.ainvoke(None, config)`
when the Telegram callback fires. The CLI adapter (which ships with the framework)
can implement `confirm()` synchronously — stdin blocks until the user hits enter.
Webhook-based adapters must bridge an external callback to the suspended coroutine.
This execution model must be explicitly specified in the Protocol documentation before
Phase 1 is called complete, so that every adapter has a concrete contract to match.

This abstraction does not currently exist in Ze. It is greenfield design work, not a
move. Getting it right is a prerequisite for everything else being genuinely portable.

---

## Project Structure

### Framework (`ze-core`)

```
ze-core/
  routing/
    router.py         # Embedding router, cosine scoring, gap threshold
    complexity.py     # In-process complexity classifier
    haiku_fallback.py # LLM fallback decomposition
    log.py            # Routing decision log interface

  capability/
    gate.py           # Gate evaluation, mode enforcement
    types.py          # Mode enum, GateDecision enum
                      # No config loader — modes live in agent classes

  memory/
    store.py          # MemoryStore Protocol
    facts.py          # Fact proposal, approval, retrieval
    episodes.py       # Episode write, archival
    consolidator.py   # Dedup, expiry, archival pipeline
    synthesizer.py    # Profile synthesis
    types.py          # Fact, Episode, UserProfile
    defaults.py       # All consolidation constants as named defaults

  goals/
    store.py          # GoalStore Protocol
    planner.py        # LLM decomposition into milestones + gates
    executor.py       # Advance loop, gate firing, milestone dispatch
    types.py          # Goal, Milestone, Gate, Learning

  proactive/
    scheduler.py      # APScheduler wrapper, persistent job store
    notifier.py       # Push delivery through Interface
    types.py          # Notification, PushType

  telemetry/
    tracker.py        # CostTracker, ContextVar attribution
    reconciler.py     # Nightly reconciliation
    types.py          # CostRecord

  orchestration/
    graph.py          # LangGraph state machine skeleton
    state.py          # AgentState TypedDict
    nodes/            # route, context, gate, execute, memory nodes
    base_agent.py     # BaseAgent, @agent decorator, tool conventions

  channels/
    base.py           # Channel Protocol (send, get_thread, poll_replies)
    registry.py       # ChannelRegistry

  interface/
    base.py           # AppInterface Protocol
    cli.py            # CLI adapter (stdin/stdout) — ships with framework
    types.py          # Message, OutboundMessage, ConfirmationRequest

  persona/
    store.py          # PersonaStore Protocol
    profile.py        # Profile, Dial, synthesis
    types.py          # PersonaProfile
    default.yaml      # Default persona shipped with the framework

  storage/
    postgres.py       # Postgres + pgvector implementations of all Protocols
    sqlite.py         # SQLite + local vector index (lightweight option)

  container.py        # Base DI container, wiring conventions
  settings.py         # Pydantic BaseSettings base class
  errors.py           # ZeCoreError hierarchy
  defaults.py         # All framework-level constants in one place
```

### Application (`ze`)

```
ze/
  agents/
    calendar/         # agent.py — model, capabilities, tools, description, system prompt
    email/            # agent.py — same
    research/         # agent.py — same
    companion/        # agent.py — same
    workflow/         # agent.py — same
    goals/            # agent.py — same
    reminders/        # agent.py — same
    prospecting/      # agent.py — same

  channels/
    email.py          # EmailChannel (Gmail API)

  contacts/           # Ze-specific: person tracking extracted from email/calendar/conversation
    store.py
    types.py
    extractors.py
    consolidator.py
    channel_store.py

  browser/            # Ze-specific: ze-browser sidecar client
    client.py
    types.py

  progress/           # Ze-specific: per-agent Telegram status messages
    reporter.py
    translations.py

  interface/
    telegram.py       # TelegramInterface implements AppInterface

  google/
    auth.py           # OAuth2 token management
    calendar.py       # Calendar API client
    gmail.py          # Gmail API client

  orchestration/
    workflow_graph.py # Ze-specific workflow execution graph (stays in ze/)

  proactive/
    briefing.py       # Morning briefing job definition
    insights.py       # Weekly insights job definition
    reminders.py      # Calendar reminder scheduler
    contacts.py       # Contact follow-up nudges
    prospecting.py    # Prospecting campaign alerts

  persona.yaml        # Ze's persona profiles — overrides framework default
                      # (currently inline in config.yaml; extracted in Phase 6)

  config/
    config.yaml       # ~30 lines after extraction: model assignments, cron schedules,
                      # persona default (currently ~200 lines including agent configs,
                      # memory thresholds, routing params — all migrated out by Phase 9)

  container.py        # Concrete DI wiring (extends ze-core Container)
  settings.py         # Concrete settings (extends ze-core BaseSettings)
  main.py             # Entry point
```

Note what is absent from `ze/` after extraction: no per-agent YAML files, no
routing config, no memory threshold config, no capability config. Each agent is one
Python file. The config is thirty lines.

### Interface vs. Channels — the distinction

Both `interface/` and `channels/` appear in ze-core. They serve different purposes
and must not be confused.

**`AppInterface`** is how Ze talks to the **user** — the person running the application.
It is bidirectional: it receives messages, sends responses, requests confirmations, and
pushes proactive notifications. There is exactly one `AppInterface` per application.
Ze implements it with Telegram. Another application implements it with Slack, a web
API, or a CLI. Everything that involves the user goes through `AppInterface`.

**`Channel`** is how agents deliver work product to **external recipients** — contacts,
third parties, the outside world. It is outbound only: send a message, retrieve a
thread, poll for replies. A `Channel` represents a communication medium (email, SMS,
LinkedIn) that Ze can use on the user's behalf. Ze implements `EmailChannel` via
Gmail. Another application might add `SlackChannel` or `SMSChannel`. An application
can have many channels registered at once.

The rule: if it involves the user interacting with Ze, it is `AppInterface`. If it
involves Ze acting in the world on the user's behalf, it is a `Channel`.

---

## The Extraction Plan

The extraction proceeds in phases. Ze continues to run throughout — the framework is
proven against the real application at every step.

### Phase 1 — Define the seams

Before moving any code, define the two critical abstractions: `MemoryStore` and
`AppInterface`. Write the Protocol definitions. Write the Postgres and Telegram
implementations without moving any business logic yet. Run Ze against the new
interfaces without changing any behaviour.

This phase is complete when:
- Ze runs identically, with all Postgres memory/goal/workflow calls going through
  `MemoryStore`, `GoalStore`, and `WorkflowStore`
- All Telegram calls go through `AppInterface`
- `AppInterface.confirm()` has a working implementation for **both** the CLI adapter
  (synchronous — stdin blocks) and the Telegram adapter (webhook-based graph resumption)

The second criterion is the harder one. `confirm()` must be validated across two
fundamentally different execution models before being declared correct. An abstraction
that only works for Telegram is not a framework abstraction.

**Why first:** If these abstractions are wrong, everything built on top of them is
wrong. Getting them right before extracting the business logic prevents expensive
rewrites later.

### Phase 2 — Extract the capability gate

The capability gate is the most self-contained primitive. It has clear inputs
(agent, intent, mode), a clear output (gate decision), and a well-defined
interaction pattern (pause, confirm, resume).

Move `ze/capability/` to `ze-core/capability/`. Remove the YAML config loader —
capability modes are now declared in agent classes, not loaded from a file. Replace
the Telegram-specific confirmation code with calls to `AppInterface.confirm()`.

**Removing `update_permanent()`:** Ze's current gate has an `update_permanent()`
method that atomically rewrites `config.yaml` to change a capability mode at runtime,
and a `PUT /capabilities/{agent}/{intent}` API endpoint that calls it. When modes
move to code, both are removed:

- `update_permanent()` is deleted — modes are source code, not runtime state
- The `PUT /capabilities/{agent}/{intent}` endpoint is removed
- The `GET /capabilities` endpoint remains, reading from the agent registry
- Per-session temporary overrides continue via `session_overrides` in `AgentState`

This phase is complete when the capability gate has no Telegram imports, no YAML
loader, no `update_permanent()`, and the confirmation flow works through the
interface abstraction.

### Phase 3 — Extract routing

Move `ze/routing/` to `ze-core/routing/`. The routing engine has no transport
dependencies — it is pure embedding math plus logging. Move routing thresholds and
embedding model selection into `ze-core/defaults.py`. Remove them from `config.yaml`.

Ensure the routing log writes through a `RoutingLog` interface (Postgres
implementation ships in `ze-core/storage/postgres.py`).

This phase is complete when the `routing:` section in Ze's `config.yaml` is
empty and routing runs on framework defaults.

### Phase 4 — Extract memory

This is the most complex extraction. Memory has three entangled parts: the store
(Postgres + pgvector), the consolidation pipeline (nightly jobs), and the injection
(called from the orchestration graph).

Extract in this order:
1. Define `MemoryStore` Protocol and move Postgres implementation to `ze-core/storage/`
2. Move all consolidation constants to `ze-core/memory/defaults.py`. Remove them
   from `config.yaml`.
3. Move memory business logic (`consolidator.py`, `synthesizer.py`) to `ze-core/memory/`
4. Move fact proposal and approval flow — ensure approval goes through `AppInterface`
5. Move the `fetch_context` orchestration node — it calls `MemoryStore`, not Postgres

Note: the fact approval flow involves editing as well as binary yes/no — the
`ConfirmationRequest` type must support this before this step can complete.

At the end of this phase, Ze's `config.yaml` has no `memory:` section.

### Phase 5 — Extract goals and proactive

Goals and proactive are relatively self-contained. Goals have no transport
dependencies except the verification gate flow (which goes through `AppInterface`
after Phase 2). Proactive has no transport dependencies except push delivery.

Note: Ze's current `ProactiveNotifier` takes `aiogram.Bot` directly. It must be
decoupled to use `AppInterface.push()` before this phase can begin. This is a
direct Telegram dependency that must be cut.

Extract both in this phase. Move the advance loop, planner, and executor to
`ze-core/goals/`. Move the scheduler and notifier to `ze-core/proactive/`.

Proactive cron schedules remain in Ze's `config.yaml` — these are genuine user
preferences, not framework constants.

### Phase 6 — Extract telemetry and persona

Both are already well-isolated in Ze. This is a near-mechanical move.

Telemetry: move tracker and reconciler to `ze-core/telemetry/`. Define a
`CostStore` interface. Move Postgres implementation to `ze-core/storage/`.

Persona: move `PersonaStore` and profile logic to `ze-core/persona/`. Ship a
`default.yaml` persona with the framework. Ze's persona profiles, currently
embedded inline in `config.yaml`, move to `ze/persona.yaml` and override the
framework default.

### Phase 7 — Migrate agent YAML files to agent classes

This phase introduces the `@agent` decorator and eliminates Ze's per-agent YAML
config entirely. It is the most visible change from the user's perspective — every
agent file gains class-level metadata that was previously split across `config.yaml`.

**What the `@agent` decorator does:**

The `@agent` decorator is Ze Core's central mechanism for making agents self-describing.
When applied to a class, it:

1. Registers the class in the agent registry (replacing Ze's current `@register` decorator)
2. Exposes class attributes to the framework: `description`, `model`, `model_simple`,
   `vision_capable`, `timeout`, `capabilities`, `intent_map`, `enabled`
3. Causes the routing engine to read `description` from the class at startup instead
   of from `settings.agent_configs`
4. Causes the capability gate to read `capabilities` from the class instead of from
   `config.yaml`
5. Causes the execution node to read `vision_capable` and `timeout` from the class
   instead of from `settings.agent_configs`

**Before and after:**

```python
# Before: ze/agents/calendar/agent.py + config.yaml agents.calendar block

# After: ze/agents/calendar/agent.py only
@agent
class CalendarAgent(BaseAgent):
    model = "anthropic/claude-haiku-4-5"
    model_simple = None          # already cheapest tier — no fallback
    vision_capable = True
    timeout = 30
    enabled = True
    description = """
        Manages Google Calendar events. Use for creating, reading, updating,
        or deleting events, checking availability, or finding free time.
    """
    capabilities = {
        "read":   Mode.AUTONOMOUS,
        "create": Mode.CONFIRM,
        "update": Mode.CONFIRM,
        "delete": Mode.CONFIRM,
    }
    intent_map = {
        "read":   "Search and retrieve calendar events.",
        "create": "Create a new calendar event.",
        "update": "Modify an existing calendar event.",
        "delete": "Remove a calendar event.",
    }
    tools = [list_events, create_event, update_event, delete_event]

    system_prompt = """..."""
```

This phase is complete when:
- The `@register` decorator is replaced by `@agent` in all agent files
- `config/agents/` is deleted
- Ze's `config.yaml` has no `agents:` section
- All eight Ze agents declare their full configuration as class attributes
- The capability gate, routing engine, and execution node read from the agent class,
  not from `settings.agent_configs`

### Phase 8 — Extract orchestration skeleton

Move the LangGraph graph compilation, `AgentState`, and the node pipeline skeleton
to `ze-core/orchestration/`. The node implementations in Ze become thin: they call
`ze-core` primitives and pass through results.

`BaseAgent`, `@agent`, and the tool conventions move to `ze-core/orchestration/`.
Ze's concrete agents stay in `ze/agents/`, implementing `BaseAgent`.

Note: `ze/orchestration/workflow_graph.py` is Ze-specific (it handles the workflow
execution graph, distinct from the main conversation graph) and stays in Ze.

### Phase 9 — Clean container and settings

Define a `Container` base class in `ze-core/container.py` that wires the core
primitives. Ze's `container.py` extends it, adding Ze-specific agents and integrations.

Define a `ZeCoreSettings` base class in `ze-core/settings.py` with only the fields
that belong to the framework: `DATABASE_URL`, `OPENROUTER_API_KEY`, `LOG_LEVEL`,
`CONFIRM_TIMEOUT_SECONDS`. Ze's `settings.py` extends it with `TELEGRAM_BOT_TOKEN`,
`GOOGLE_CLIENT_ID`, and so on.

At the end of this phase, starting a new application means: subclass `Container`,
point it at a config file, and put agents in the `agents/` directory. The framework
discovers agents automatically, starts the scheduler, compiles the graph, connects
the interface, and runs.

**Ze's final `config.yaml` at the end of all phases:**

```yaml
models:
  router:    anthropic/claude-haiku-4-5
  synthesis: anthropic/claude-haiku-4-5

persona:
  profile: default

proactive:
  briefing:
    cron: "0 8 * * *"
  calendar:
    sync_cron: "45 7 * * *"
    sync_days_ahead: 7
  insights:
    cron: "0 7 * * 0"
    category_cooldown_days: 7
  alerts:
    workflow_failure_cooldown_hours: 1
```

Everything else is a convention.

---

## What Building on Ze Core Looks Like

A developer building a new application on Ze Core writes agents, an interface
adapter, and a short config file. The framework handles everything else.

```python
# myapp/agents/research.py
from ze_core.orchestration import BaseAgent, agent
from ze_core.capability import Mode

@agent
class ResearchAgent(BaseAgent):
    model = "anthropic/claude-sonnet-4-5"
    model_simple = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    description = """
        Handles web searches, fact-finding, and research synthesis.
        Use when the user asks to look something up, research a topic,
        or needs current information from the web.
    """
    capabilities = {
        "read":    Mode.AUTONOMOUS,
        "execute": Mode.CONFIRM,
    }
    tools = [web_search, fetch_url, summarize]

    system_prompt = """
    You are a research assistant. Search thoroughly before answering.
    Always cite your sources.
    """
```

```python
# myapp/agents/writer.py
from ze_core.orchestration import BaseAgent, agent
from ze_core.capability import Mode

@agent
class WriterAgent(BaseAgent):
    model = "anthropic/claude-sonnet-4-5"
    timeout = 60
    description = """
        Drafts, edits, and improves written content.
        Use when the user wants to write something, refine existing text,
        or get feedback on writing.
    """
    capabilities = {
        "create": Mode.DRAFT_ONLY,
        "reason": Mode.AUTONOMOUS,
    }
    tools = []

    system_prompt = """
    You are a writing assistant. Be direct and concrete.
    """
```

```python
# myapp/interface/slack.py
from ze_core.interface import AppInterface, OutboundMessage, ConfirmationRequest

class SlackInterface(AppInterface):
    async def send(self, message: OutboundMessage) -> None: ...
    async def confirm(self, request: ConfirmationRequest): ...
    async def push(self, notification) -> None: ...
```

```python
# myapp/container.py
from ze_core.container import Container
from myapp.interface.slack import SlackInterface

class MyAppContainer(Container):
    interface = SlackInterface
```

```python
# myapp/main.py
from myapp.container import MyAppContainer

container = MyAppContainer.from_config("config.yaml")
container.run()
# Ze Core scans myapp/agents/ automatically, imports every agent.py it finds,
# and @agent handles registration. No explicit agent list needed.
```

```yaml
# config.yaml — the entire config file
models:
  router:    anthropic/claude-haiku-4-5
  synthesis: anthropic/claude-haiku-4-5

persona:
  profile: default

proactive:
  briefing:
    cron: "0 9 * * *"
```

The framework starts the scheduler, compiles the orchestration graph, connects the
Slack interface, and begins processing messages. The application author wrote two
agent files, one interface adapter, one container, and twelve lines of config.

They did not wire a router, implement a confirmation flow, build a memory
consolidation pipeline, write a cost tracker, manage a capability config file, or
create per-agent YAML files.

---

## What Ze Core Does Not Do

Ze Core is deliberately scoped. It does not:

- Support multiple simultaneous users. The identity model is single-user. Multi-tenancy
  is out of scope.
- Provide a visual graph editor. The code is the interface.
- Abstract LLM providers beyond what OpenRouter already provides. Model selection is
  configuration, not a framework concern.
- Implement specific integrations. Google Calendar, Gmail, Slack — these are
  application concerns. Ze Core provides the `Channel` and `AppInterface` abstractions;
  applications provide the implementations.
- Handle auth for end users. Single-user applications don't have login flows.
- Offer a hosted deployment. Ze Core is self-hosted by design. The user owns their
  data and their infrastructure.
- Expose configuration knobs for things that should just work. If you need to tune
  a memory consolidation threshold, you override it in code, not in a YAML file.

---

## Design Decisions Worth Preserving

Several decisions in Ze are non-obvious and worth encoding explicitly as Ze Core
conventions rather than leaving them to application authors.

**The graph is compiled once at startup.** Not reconstructed per request.
The compiled graph is stored on application state and invoked per message with a
`thread_id`. This matters for performance and for the human-in-the-loop pattern
(interrupted graphs resume from checkpoints).

**`AgentState` must be JSON-serialisable at all times.** The checkpoint mechanism
depends on this. Any state that cannot be serialised to JSON has no place in
`AgentState`. Image bytes, for example, should be stored separately with only the
routing caption in state. Ze's current implementation has a known exception here
(`image_data: bytes | None` in `AgentState`) that the extraction must resolve.

**Agents cannot call each other directly.** Compound coordination goes through the
orchestration graph. Agents are peers; none orchestrates another. This prevents
implicit coupling and keeps the capability gate in the coordination path.

**The identity block is assembled by the framework, not by agents.** Agents define
only their task-specific system prompt. The framework assembles the full system
prompt: identity, persona, memory context, agent instructions — in that order.
Agents never inject memory or persona themselves.

**Reviewed facts are never auto-modified.** A reviewed fact represents an explicit
user decision. The consolidation pipeline will deduplicate and expire unreviewed
facts, but it will never touch a reviewed one. This invariant is enforced in the
store implementation, not just documented as convention.

**Capability modes belong in code, not config.** Ze Core encodes this as a convention
enforced through the `@agent` decorator. Ze's current `config.yaml` loads capability
modes from a YAML block alongside agent descriptions and model assignments — a coupling
that makes both harder to reason about. The extraction moves these into the agent class
definition where they are visible in code review and changed deliberately, not
accidentally by editing a file. This is achieved in Phase 7.

**LangGraph is the orchestration convention.** Ze Core uses LangGraph. This is a
deliberate convention, not a plugin point. `AgentState` as a `TypedDict`, graph
compilation at startup, `thread_id` per conversation, and `graph.ainvoke(None, config)`
for confirmation resumption are all framework assumptions. If you want a different
orchestration layer, Ze Core is not your framework.

---

## Open Questions Before Implementation

Several decisions need to be resolved before Phase 1 begins.

**`AppInterface.confirm()` execution model.** Define the expected contract before
writing a single line of Phase 1 code. The CLI adapter is the reference implementation
— it blocks synchronously on stdin. The Telegram adapter must bridge an HTTP callback
to a suspended coroutine (via LangGraph checkpoint resumption). The exact mechanism
— whether `confirm()` uses an `asyncio.Event`, a queue, or another primitive — must
be specified before both adapters are written, so they have a concrete contract to
match rather than each inventing their own solution.

**Name the second application before Phase 1.** Success criterion 5 (a second
application running on Ze Core) is the most important validation. Don't leave it
abstract. A Slack-based research companion — two agents (research, writing), SQLite
storage, no Google integration — would exercise a different interface, a different
storage backend, and a minimal agent surface. Name it before Phase 1 begins so the
abstractions are shaped by two applications from the start, not one.

**`update_permanent()` replacement.** Ze currently allows capability mode changes at
runtime via the `PUT /capabilities/{agent}/{intent}` API endpoint. With modes in code,
permanent changes require editing the agent class and redeploying. Decide before Phase 2
whether any form of runtime override that survives process restarts is a framework
concern. The existing `session_overrides` mechanism provides per-invocation overrides.
If persistent runtime overrides are needed, they require a persistence layer. If not,
remove the endpoint cleanly and document the change.

**Package distribution.** Should `ze-core` be published to PyPI as an installable
package, or distributed as a Git dependency? PyPI requires versioning discipline and
a stable public API from the start. Git dependency is faster to iterate but harder
to document. Given that Ze Core will be under active development during extraction,
a Git dependency is the right starting point.

**CLI adapter as the minimum viable interface.** The Telegram implementation will
move to `ze/`. The framework should ship a CLI adapter (stdin/stdout) so developers
can test their agents without running a bot. This is the minimum viable interface
and should be the first adapter written against `AppInterface`.

**SQLite storage implementation.** The Postgres implementation is the default and
is proven. A SQLite implementation would significantly lower the barrier to getting
started — no Postgres to provision, no pgvector extension to install. Approximate
vector search (e.g. via a numpy cosine scan) is sufficient for development and
low-volume personal use. Worth building early, alongside the second application.

**Versioning and migration strategy.** Ze's database schema will diverge from Ze Core's
schema as the extraction proceeds. A migration strategy needs to be defined before
Phase 4 (memory extraction) to ensure Ze's existing data survives.

**`defaults.py` governance.** All framework constants will live in
`ze-core/defaults.py`. Expose the five or six most likely overrides (routing
thresholds, consolidation cron) on `Container`. Require subclassing for anything
more exotic. Decide this before Phase 3 so there is no ambiguity about where
constants live when routing is extracted.

---

## Success Criteria

Ze Core is successful when:

1. Ze runs on Ze Core with no degradation in behaviour or performance.
2. Ze's `config.yaml` is thirty lines or fewer. No per-agent YAML files. No routing
   config. No memory threshold config.
3. A developer unfamiliar with Ze's internals can build a working persistent AI
   application — with memory, capability gates, and a scheduled proactive job — in
   a weekend, using only the Ze Core documentation.
4. The Telegram dependency is completely absent from `ze-core/`. Ze's Telegram
   integration lives entirely in `ze/interface/telegram.py`.
5. A second application (not Ze) runs on Ze Core, proving that the abstractions
   generalize beyond the original use case.

The fifth criterion is the hardest and the most important. Until a second application
runs on the framework, the extraction is reorganization, not generalization.
