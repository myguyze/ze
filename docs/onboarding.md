# Onboarding

Ze onboarding is a plugin-extensible setup flow. It lets plugins ask for meaningful
first-run information, renders those questions with server-driven UI, reviews durable
memory/settings before saving them, and supports scoped personal-data reset for local
development or re-onboarding.

## Package Boundary

Reusable onboarding logic lives in `core/ze-onboarding`:

- `ze_onboarding.types` defines provider, step, field, seed, store, persistence, view, and
  reset dataclasses/protocols.
- `ze_onboarding.coordinator.OnboardingCoordinator` orders providers, dispatches
  submissions, inserts the review step, and applies approved seeds through protocols.
- `ze_onboarding.providers.CoreOnboardingProvider` provides minimal built-in setup.

Deployment adapters live in `apps/ze-api`:

- `ze_api.api.websocket.onboarding.send_onboarding_view()` serialises onboarding views
  into WebSocket `message` frames.
- `ze_api.api.websocket.component_submit.handle_component_submit()` routes onboarding
  submissions back into the coordinator.
- `ze_api.api.websocket.commands.handle_command()` starts onboarding on demand.
- `ze_api.container` wires the Postgres-backed store, persistence adapter, and reset
  service into `OnboardingCoordinator`.

Plugin authors should import from `ze_sdk.onboarding`, not from `ze_api`.

## Plugin Opt-In

Plugins opt in by returning an onboarding provider from `ZePlugin.onboarding()`.

```python
from ze_sdk import ZePlugin
from ze_sdk.onboarding import (
    OnboardingField,
    OnboardingResult,
    OnboardingSeed,
    OnboardingStep,
    OnboardingSubmission,
)


class NewsOnboardingProvider:
    plugin_name = "ze_news"
    priority = 20

    async def steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                id="ze_news.preferences",
                plugin=self.plugin_name,
                title="Choose news preferences",
                kind="form",
                fields=[
                    OnboardingField(
                        id="topics",
                        label="Topics you care about",
                        field_type="chips",
                        placeholder="AI, Portugal, markets",
                    ),
                    OnboardingField(
                        id="excluded_topics",
                        label="Topics to avoid",
                        field_type="chips",
                        required=False,
                    ),
                ],
            )
        ]

    async def handle_submission(
        self,
        submission: OnboardingSubmission,
    ) -> OnboardingResult:
        return OnboardingResult(seeds=[
            OnboardingSeed(
                kind="profile_facet",
                key="news_interests",
                value=submission.values.get("topics", []),
                plugin=self.plugin_name,
                source_step_id=submission.step_id,
            ),
            OnboardingSeed(
                kind="profile_facet",
                key="news_exclusions",
                value=submission.values.get("excluded_topics", []),
                plugin=self.plugin_name,
                source_step_id=submission.step_id,
            ),
        ])


class NewsPlugin(ZePlugin):
    def onboarding(self) -> NewsOnboardingProvider:
        return NewsOnboardingProvider()
```

Providers should be deterministic. If the same submission is processed twice, it should
produce equivalent seeds and follow-up steps.

## Seed Model

Providers do not write directly to global memory or plugin tables. They return typed
`OnboardingSeed` values. The coordinator stores those seeds and shows review-required
items before applying them.

Supported seed kinds in the first implementation:

- `profile_facet`: persisted to `memory_profile_facets`.
- `memory_fact`: persisted through the memory store as a reviewed fact.
- `plugin_setting`: persisted through a registered plugin setting setter.

Other planned seed kinds are modeled but not fully implemented yet:

- `capability_request`
- `contact`
- `channel_connection`

## WebSocket Flow

The app starts onboarding by sending:

```json
{ "type": "command", "name": "onboarding" }
```

The backend replies with a normal assistant message plus onboarding metadata:

```json
{
  "type": "message",
  "message": {
    "role": "assistant",
    "text": "Tell Ze the basics",
    "components": [{ "type": "form", "id": "core.profile", "title": "Tell Ze the basics" }]
  },
  "onboarding": {
    "session_id": "2cf6...",
    "completed": false
  }
}
```

Interactive onboarding components submit structured payloads:

```json
{
  "type": "component_submit",
  "session_id": "2cf6...",
  "step_id": "core.profile",
  "component_id": "core.profile",
  "values": {
    "preferred_name": "Joao",
    "timezone": "Europe/Lisbon"
  }
}
```

Outside onboarding, existing form and confirm components still fall back to chat-text
submission for compatibility.

## Reset Scopes

`ResetService` supports previewing and executing scoped resets. Execution requires
`confirm: "RESET"` and should be exposed only through high-friction UI.

- `memory`: learned memory tables and legacy memory tables.
- `personal_state`: memory plus messages, pending confirmations, contacts, goals,
  workflows, reminders, news cache, checkpoints, and onboarding tables.
- `full_dev`: reserved for external database recreate tooling; not executed through
  `ResetService`.

Preview over WebSocket:

```json
{ "type": "command", "name": "reset_preview", "scope": "personal_state" }
```

Execute over WebSocket:

```json
{
  "type": "command",
  "name": "reset",
  "scope": "personal_state",
  "confirm": "RESET"
}
```

Do not log raw onboarding submissions; they may contain sensitive user data.
