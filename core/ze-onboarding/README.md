# ze-onboarding

Plugin-extensible onboarding coordinator — setup flow contracts, step/seed types, and reset domain types.

## Responsibilities

| Module | What it provides |
|---|---|
| `coordinator.py` | `OnboardingCoordinator` — orchestrates multi-plugin setup flows |
| `providers.py` | `CoreOnboardingProvider`, `OnboardingProvider` protocol |
| `types.py` | Steps, seeds, sessions, reset scope, persistence contracts |

## Dependencies

```mermaid
graph LR
    onboarding[ze-onboarding] --> agents[ze-agents]
```

## Usage

Plugins contribute onboarding steps via `ZePlugin.onboarding()`. The coordinator in `ze-api` drives the setup flow and persists progress:

```python
from ze_onboarding import OnboardingCoordinator, OnboardingProvider
from ze_sdk.onboarding import OnboardingStep, OnboardingSeed
```

## Testing

From the repo root:

```bash
make test-onboarding
```

See [docs/testing.md](../../docs/testing.md).
