# Onboarding Platform — Spec

> **Packages:** `ze-onboarding`, `ze-sdk`, `ze-components`, `ze-api`, `ze-app`
> **Phase:** 51
> **Status:** Done
> **Depends on:** Phase 41 ([41-component-descriptors.md](41-component-descriptors.md)), Phase 42 ([42-native-ui-foundation.md](42-native-ui-foundation.md)), Phase 47 ([47-plugin-framework.md](47-plugin-framework.md)), Phase 49 ([49-ze-sdk.md](49-ze-sdk.md)), Phase 50 ([50-news-preferences.md](50-news-preferences.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| Personal data reset command | ✅ Implemented |
| Onboarding SDK contract | ✅ Implemented |
| Core onboarding coordinator | ✅ Implemented |
| Postgres onboarding store | ✅ Implemented |
| Component submission protocol | ✅ Implemented |
| Expanded onboarding components | ✅ Implemented |
| Flutter onboarding UI | ✅ Implemented |
| Plugin onboarding providers | ✅ Implemented |
| Tests | ✅ Implemented |

---

## Purpose

Ze needs a deliberate first-run setup path. Today the assistant learns passively from
conversation, memory extraction, contacts consolidation, and plugin-specific stores. That
works once the system has history, but it makes a fresh install feel empty and makes
local development hard after memory has accumulated noisy facts, episodes, and stale
preferences.

This phase introduces a plugin-extensible onboarding platform. Plugins can declare the
information they need to provide a useful first experience, Ze renders those requests as
server-driven UI, and the runtime persists approved answers into memory or plugin stores
through typed contracts. The same phase also adds an explicit personal data reset path so
the user can wipe learned state and re-run onboarding safely.

---

## Responsibilities

- Provide a safe, explicit reset path for personal learned state.
- Define a stable `ze_sdk.onboarding` authoring contract for plugin onboarding providers.
- Let every plugin opt into onboarding without importing `ze_api` or graph internals.
- Coordinate onboarding centrally so plugins cannot directly own global setup flow.
- Render onboarding steps through `ze-components` and the native app.
- Accept structured component submissions over WebSocket instead of treating form data as
  plain chat text.
- Persist onboarding progress so setup can resume after reconnect, app restart, or partial
  completion.
- Persist collected data through typed seeds: memory facts/profile facets, plugin settings,
  capability requests, contacts, and channel connections.
- Keep onboarding reviewable: show the user what will be remembered before writing durable
  memory.

---

## Out of Scope

- Multi-user onboarding. Ze is still a single-user assistant.
- A plugin marketplace review/permission model.
- Runtime plugin installation from the app.
- Arbitrary plugin-defined database writes during onboarding. Plugins return typed seeds;
  the coordinator decides how to persist them.
- Replacing normal chat with a general workflow/form engine.
- Browser automation for OAuth. Account connection steps may deep-link or instruct, but
  this phase does not implement OAuth providers.
- Inference-only onboarding where the model silently decides preferences without review.

---

## Design Principles

1. **Onboarding is structured setup, not chat text.** Form and button submissions should
   travel as typed frames with step IDs and values.
2. **Plugins describe needs; the platform owns flow.** A plugin can ask for fields,
   choices, consent, or account connection, but cannot decide global ordering alone.
3. **Memory writes are reviewed.** Durable facts and profile facets from onboarding are
   shown in a review step before commit.
4. **Reset is scoped and reversible only by backup.** Commands must make the chosen scope
   explicit. There is no accidental "clean everything" shortcut.
5. **SDK surface stays small.** Plugin authors get dataclasses and protocols. Coordinator,
   WebSocket, DB pool, and app internals stay out of `ze-sdk`.

---

## Module Locations

```text
core/ze-onboarding/
  ze_onboarding/
    __init__.py
    types.py                # dataclasses, provider/store/persistence protocols
    coordinator.py          # flow assembly, review step, submission dispatch
    providers.py            # built-in core setup provider

core/ze-sdk/
  ze_sdk/
    onboarding.py           # re-export ze_onboarding symbols

core/ze-agents/
  ze_agents/
    plugin.py               # ZePlugin.onboarding() opt-in hook
    onboarding/             # compatibility re-export of ze_onboarding

core/ze-components/
  ze_components/
    types.py                # add onboarding-friendly components/fields
    tools.py                # render tools for new components

apps/ze-api/
  ze_api/
    onboarding/
      __init__.py
      store.py              # Postgres adapter for ze_onboarding.OnboardingStore
      persistence.py        # applies typed seeds to memory/plugin stores
      reset.py              # SQL implementation for personal-state reset
    api/
      ws.py                 # component_submit frames and onboarding command
    migrations/
      versions/
        007_onboarding.py

apps/ze-app/
  lib/src/onboarding/
    onboarding_screen.dart
    onboarding_controller.dart
  lib/src/components/widgets/
    choice_group_widget.dart
    consent_widget.dart
    connect_account_widget.dart
    review_widget.dart
```

The reusable onboarding domain belongs in `core/ze-onboarding`, not `ze-api`.
`ze-api` owns only deployment adapters: SQL, WebSocket frames, reset execution, and
container wiring.

---

## Public SDK Contract

Plugin authors import onboarding symbols from `ze_sdk.onboarding`, which re-exports
`ze_onboarding`. Runtime internals can import directly from `ze_onboarding`.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


OnboardingStepKind = Literal[
    "intro",
    "form",
    "choice",
    "consent",
    "connect_account",
    "review",
]


SeedKind = Literal[
    "memory_fact",
    "profile_facet",
    "plugin_setting",
    "capability_request",
    "contact",
    "channel_connection",
]


@dataclass(frozen=True)
class OnboardingField:
    id: str
    label: str
    field_type: Literal[
        "text",
        "textarea",
        "number",
        "date",
        "select",
        "multiselect",
        "boolean",
        "chips",
    ] = "text"
    required: bool = True
    placeholder: str | None = None
    options: list[str] | None = None
    help_text: str | None = None


@dataclass(frozen=True)
class OnboardingChoice:
    id: str
    label: str
    description: str | None = None
    recommended: bool = False


@dataclass(frozen=True)
class OnboardingStep:
    id: str
    plugin: str
    title: str
    kind: OnboardingStepKind
    description: str | None = None
    fields: list[OnboardingField] = field(default_factory=list)
    choices: list[OnboardingChoice] = field(default_factory=list)
    allow_multiple: bool = False
    required: bool = True
    depends_on: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OnboardingSubmission:
    step_id: str
    values: dict[str, Any]


@dataclass(frozen=True)
class OnboardingSeed:
    kind: SeedKind
    key: str
    value: Any
    confidence: float = 1.0
    source_step_id: str | None = None
    plugin: str | None = None
    review_required: bool = True


@dataclass(frozen=True)
class OnboardingResult:
    seeds: list[OnboardingSeed] = field(default_factory=list)
    next_steps: list[OnboardingStep] = field(default_factory=list)
    complete: bool = False


class OnboardingProvider(Protocol):
    plugin_name: str
    priority: int

    async def steps(self) -> list[OnboardingStep]:
        """Return this plugin's initial onboarding steps."""

    async def handle_submission(
        self,
        submission: OnboardingSubmission,
    ) -> OnboardingResult:
        """Validate one submission and return typed seeds or follow-up steps."""
```

`ZePlugin` gains a default no-op hook:

```python
class ZePlugin(ABC):
    def onboarding(self) -> OnboardingProvider | None:
        return None
```

`ze-sdk` re-exports provider/step/seed symbols only. The coordinator lives in
`ze-onboarding`; Postgres storage, seed persistence, reset SQL, and WebSocket integration
remain private to `ze-api`.

---

## Coordinator Contract

The coordinator is implemented in `ze_onboarding.coordinator`. It depends on protocols,
not concrete database or API types.

```python
class OnboardingCoordinator:
    def __init__(
        self,
        *,
        providers: list[OnboardingProvider],
        store: OnboardingStore,              # protocol from ze_onboarding.types
        persistence: OnboardingPersistence,  # protocol from ze_onboarding.types
    ) -> None: ...

    async def start(self) -> OnboardingSession: ...

    async def get_current(self, session_id: UUID) -> OnboardingView: ...

    async def submit(
        self,
        session_id: UUID,
        step_id: str,
        values: dict[str, Any],
    ) -> OnboardingView: ...

    async def complete(self, session_id: UUID) -> None: ...
```

The coordinator owns:

- deterministic provider ordering by `(priority, plugin_name)`
- dependency checks between steps
- validation that submissions reference active steps
- accumulation of pending seeds
- insertion of review steps before durable writes
- persistence only after user approval
- completion state per plugin and step

Providers must be deterministic and idempotent. A repeated `handle_submission()` call for
the same values must return equivalent seeds.

---

## Database Schema

```sql
CREATE TABLE onboarding_sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'completed', 'cancelled')),
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE onboarding_steps (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID NOT NULL REFERENCES onboarding_sessions(id) ON DELETE CASCADE,
    plugin         TEXT NOT NULL,
    step_key       TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'active', 'completed', 'skipped')),
    descriptor     JSONB NOT NULL,
    submission     JSONB,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    UNIQUE(session_id, plugin, step_key)
);

CREATE TABLE onboarding_seeds (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID NOT NULL REFERENCES onboarding_sessions(id) ON DELETE CASCADE,
    step_id        UUID REFERENCES onboarding_steps(id) ON DELETE SET NULL,
    plugin         TEXT,
    kind           TEXT NOT NULL,
    key            TEXT NOT NULL,
    value          JSONB NOT NULL,
    confidence     FLOAT NOT NULL DEFAULT 1.0,
    review_status  TEXT NOT NULL DEFAULT 'pending'
                   CHECK (review_status IN ('pending', 'approved', 'rejected', 'applied')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at     TIMESTAMPTZ
);

CREATE INDEX onboarding_sessions_status_idx
    ON onboarding_sessions (status, updated_at DESC);

CREATE INDEX onboarding_steps_session_status_idx
    ON onboarding_steps (session_id, status, created_at);

CREATE INDEX onboarding_seeds_session_status_idx
    ON onboarding_seeds (session_id, review_status, created_at);
```

No plugin-specific onboarding tables are required for v1.

---

## Seed Persistence

The coordinator applies approved seeds through `OnboardingPersistence`.

| Seed kind | Destination |
| --------- | ----------- |
| `memory_fact` | `ze_memory.MemoryStore.propose_facts()` with high confidence and onboarding source refs |
| `profile_facet` | `memory_profile_facets` via a memory-store method added in this phase |
| `plugin_setting` | A plugin-owned setter registered in `OnboardingPersistence` |
| `capability_request` | Capability gate override flow, possibly requiring confirmation |
| `contact` | `PersonStore` / contact channel stores |
| `channel_connection` | Channel/account connection registry or pending connection state |

For v1, the persistence layer should support memory facts, profile facets, and plugin
settings first. Contacts and channel connections can be implemented as supported seed
kinds with no active producers until the corresponding plugins opt in.

---

## Component Extensions

Existing `FormComponent` is useful but too small for onboarding. This phase extends the
component system from Python dataclasses and regenerates Dart models.

### Field Improvements

`FormField` gains:

- `textarea`
- `multiselect`
- `boolean`
- `chips`
- `required`
- `help_text`
- `default_value`

### New Components

```python
@dataclass
class ChoiceOption:
    id: str
    label: str
    description: str | None = None
    recommended: bool = False


@dataclass
class ChoiceGroupComponent:
    id: str
    title: str
    options: list[ChoiceOption]
    allow_multiple: bool = False
    description: str | None = None
    submit_label: str = "Continue"
    type: Literal["choice_group"] = field(default="choice_group", init=False)


@dataclass
class ConsentScope:
    id: str
    label: str
    description: str
    required: bool = True


@dataclass
class ConsentComponent:
    id: str
    title: str
    body: str
    scopes: list[ConsentScope]
    accept_label: str = "Allow"
    reject_label: str = "Skip"
    type: Literal["consent"] = field(default="consent", init=False)


@dataclass
class ConnectAccountComponent:
    id: str
    provider: str
    title: str
    description: str
    status: Literal["not_connected", "connected", "error"] = "not_connected"
    action_label: str = "Connect"
    type: Literal["connect_account"] = field(default="connect_account", init=False)


@dataclass
class ReviewItem:
    id: str
    label: str
    value: str
    kind: str
    plugin: str | None = None


@dataclass
class ReviewComponent:
    id: str
    title: str
    items: list[ReviewItem]
    approve_label: str = "Save"
    reject_label: str = "Edit"
    type: Literal["review"] = field(default="review", init=False)
```

All interactive onboarding components must include a stable `id`. The app uses that ID in
submission frames.

---

## WebSocket Protocol

Current form and confirm components submit regular chat text. Onboarding requires a typed
frame:

```json
{
  "type": "component_submit",
  "component_id": "news-topics",
  "session_id": "bbf2...",
  "step_id": "ze_news.preferences",
  "values": {
    "topics": ["AI", "Portugal", "markets"]
  }
}
```

Backend response:

```json
{
  "type": "message",
  "message": {
    "role": "assistant",
    "text": "Great, I will use these as starting preferences.",
    "components": [
      { "type": "review", "id": "review-memory", "title": "What Ze will remember", "items": [] }
    ]
  }
}
```

The WebSocket handler routes `component_submit` to `OnboardingCoordinator.submit()` when
`session_id` maps to an active onboarding session. Outside onboarding, it may return:

```json
{ "type": "error", "detail": "Unknown component submission." }
```

This phase does not require general component callbacks for arbitrary agent messages,
but the protocol should be reusable later.

---

## Reset Service

The reset service provides explicit scopes.

```python
ResetScope = Literal["memory", "personal_state", "full_dev"]


class ResetService:
    async def preview(self, scope: ResetScope) -> ResetPreview: ...
    async def reset(self, scope: ResetScope, *, confirm: str) -> ResetResult: ...
```

### Scope: `memory`

Wipes learned memory only:

- `memory_relationships`
- `memory_profile_facets`
- `memory_task_state`
- `memory_procedures`
- `memory_events`
- `memory_facts`
- `memory_entities`
- `memory_episodes`
- legacy `user_facts`
- legacy `episodes`
- legacy `user_profile`

`user_profile` should be re-seeded with its default row if existing code expects a
single-row profile.

### Scope: `personal_state`

Includes `memory`, plus user-facing persisted state:

- `messages`
- `pending_confirmations`
- `contacts`
- `contact_sources`
- `contact_relationships`
- `contact_channels`
- `goals`
- `goal_milestones`
- `goal_gates`
- `goal_learnings`
- `goal_execution_traces`
- `goal_suggestions`
- `workflows`
- `workflow_executions`
- `user_reminders`
- `calendar_reminders`
- `insights`
- `prospect_campaigns`
- `prospect_outreach`
- `news_articles`
- `onboarding_sessions`
- `onboarding_steps`
- `onboarding_seeds`

It should preserve:

- Alembic migration tables
- LangGraph checkpoint table structure, but delete rows from `checkpoints`,
  `checkpoint_blobs`, and `checkpoint_writes`
- `llm_cost_log`
- `routing_log`
- `capability_overrides`, unless the user chooses an additional reset flag

### Scope: `full_dev`

For local development only. Prefer a database recreate path through existing Makefile or
migration tooling instead of a giant table list. This scope must not be exposed casually
in the app UI.

### User Interaction

The app should surface reset as a high-friction settings action:

1. Show preview counts by table/category.
2. Require typing `RESET`.
3. Execute reset.
4. Start onboarding automatically.

CLI/API support can come first for development:

```bash
make reset-personal-state
```

---

## First-Run Flow

1. App connects to `/ws`.
2. Backend detects no completed onboarding session.
3. Backend sends an onboarding intro message with a progress component.
4. Coordinator gathers provider steps.
5. User completes steps one at a time.
6. Provider submissions return typed seeds and optional follow-up steps.
7. Coordinator renders a review step for durable memory/settings.
8. User approves.
9. Persistence applies seeds.
10. Session is marked `completed`.
11. Normal chat resumes.

The user can skip optional plugin steps. Required core steps should be minimal:

- name or preferred form of address
- timezone/locale if calendar/reminders are enabled
- broad assistant preferences
- consent/review for what Ze will remember

---

## Plugin Examples

### News

`ze-news` can ask:

- preferred topics
- excluded topics
- source/language preference
- credibility strictness
- feed diversity preference

It returns seeds:

- `profile_facet: news_interests`
- `profile_facet: news_exclusions`
- `plugin_setting: ze_news.credibility_threshold`
- `plugin_setting: ze_news.discovery_ratio`

This makes Phase 50 stronger because explicit news preferences are collected before the
news agent has to infer them from incidental memory.

### Calendar

`ze-calendar` can ask:

- timezone
- reminder defaults
- whether calendar sync should be enabled

It returns:

- `profile_facet: timezone`
- `plugin_setting: ze_calendar.default_reminder_offsets`
- `channel_connection: google_calendar`

### Personal

`ze-personal` can ask:

- preferred name
- communication style
- important current goals
- people/organizations the user wants Ze to know about

It returns:

- `memory_fact`
- `profile_facet`
- `contact`

Contacts should stay review-required by default.

---

## Configuration

```yaml
onboarding:
  enabled: true
  auto_start_on_empty_profile: true
  require_review: true
  reset:
    allow_full_dev_from_app: false
```

Plugins do not configure onboarding in YAML for v1. They expose providers from code via
`ZePlugin.onboarding()`.

---

## Implementation Plan

1. Add reset preview/reset service and a developer command for `memory` and
   `personal_state`.
2. Add `ze_agents.onboarding` types and re-export them from `ze_sdk.onboarding`.
3. Add `ZePlugin.onboarding()` default hook.
4. Add onboarding migrations and `OnboardingStore`.
5. Add `OnboardingCoordinator` with one built-in core provider.
6. Extend component dataclasses and regenerate Flutter descriptors.
7. Add `component_submit` outbound app frame and backend handler.
8. Build Flutter onboarding widgets/screens for the new components.
9. Add first plugin providers, starting with `ze-news` and `ze-personal`.
10. Add tests for reset scopes, provider discovery, submissions, persistence, and app
    protocol parsing.

---

## Test Plan

- Unit-test `ResetService.preview()` and `ResetService.reset()` against mocked asyncpg
  connections, verifying table order avoids FK failures.
- Unit-test `OnboardingCoordinator` ordering, skip behavior, review insertion, and
  idempotent repeated submissions.
- Unit-test seed persistence for memory facts, profile facets, and plugin settings.
- Unit-test `ZePlugin.onboarding()` discovery from active plugin instances.
- Unit-test WebSocket parsing for `component_submit`.
- Add Flutter widget tests for form, choice, consent, connection, and review submission.
- Add integration test: empty DB -> app connects -> onboarding starts -> submit news
  preferences -> review -> seeds persisted.

---

## Security and Privacy

- Reset commands are destructive and must require explicit confirmation.
- Onboarding submissions may contain sensitive personal data; do not log raw values.
- Store component descriptors and submissions in JSONB, but redact or avoid storing secrets.
- Account connection steps should never store OAuth tokens in onboarding tables.
- Memory seeds must include provenance so later profile/memory views can show that a fact
  came from onboarding.

---

## Open Questions

- [ ] Should `capability_overrides` be preserved by default during `personal_state` reset?
  Initial recommendation: preserve them, because they are safety policy rather than learned
  memory.
- [ ] Should onboarding launch as a dedicated screen or as a chat thread with rich
  components? Initial recommendation: dedicated screen backed by the same component
  descriptors, because setup needs clear progress and fewer chat affordances.
- [ ] Should plugin settings get a generic key/value store, or should each plugin register
  a setter? Initial recommendation: register setters to avoid creating an untyped settings
  dumping ground.
- [ ] Should onboarding be rerunnable per plugin after completion? Initial recommendation:
  yes, but via settings after v1.
