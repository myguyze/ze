# Capability Gate — Spec

> **Status:** Deprecated — superseded by [`core/03-capability-gate.md`](../core/03-capability-gate.md)
>
> This spec describes the original YAML-based capability system (Phase 2). The current
> implementation uses class attributes on `@agent` classes (no `capabilities.yaml`).
> See `core/03-capability-gate.md` for the authoritative spec.

---

## Purpose

Authorise or restrict agent tool execution based on per-agent, per-intent
permission configuration. Supports session-scoped escalation (temporary) and
permanent overrides (written back to YAML). This is the sole enforcement point
for Ze's permission model — no agent checks permissions itself.

## Responsibilities

- Load `config/capabilities.yaml` at startup via `ze/settings.py`.
- Hot-reload configuration on `SIGHUP` (Unix signal, Fly.io compatible).
- Evaluate `(agent, intent)` pairs against loaded config and session overrides.
- Return a `GateDecision` for every evaluation request.
- Enforce the escalation ceiling: session overrides cannot elevate `draft_only`
  to `execute`. Only a YAML change can do that.
- Write YAML updates atomically (write to temp file, rename) for permanent overrides.

## Out of Scope

- Does not select which tool to call.
- Does not execute tools.
- Does not handle authentication or OAuth tokens.
- Does not validate that the agent or intent actually exists in the system.

## Interface Contract

### Input

```python
agent: str                                  # e.g. "calendar"
intent: str                                 # e.g. "create"
session_overrides: dict[str, str]           # agent.intent → mode string
                                            # e.g. {"calendar.create": "autonomous"}
```

### Output

```python
GateDecision  # EXECUTE | DRAFT | AWAIT_CONFIRMATION | BLOCKED
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Agent disabled (`enabled: false`) | Return `BLOCKED` immediately, skip intent check |
| Unknown `agent.intent` key in config | Default to `AWAIT_CONFIRMATION`, log warning |
| Session says `autonomous`, config says `disabled` | `BLOCKED` wins — hard ceiling |
| Session tries to escalate `draft_only` to `autonomous` | `DRAFT` — ceiling enforced |
| Config file unreadable at startup | Raise `CapabilityConfigError`, abort startup |
| Config file unreadable at SIGHUP | Log error, retain previous config, continue |

## Data Structures

Lives in `ze/capability/types.py`.

```python
from enum import Enum
from dataclasses import dataclass

class GateDecision(Enum):
    EXECUTE             = "execute"
    DRAFT               = "draft"
    AWAIT_CONFIRMATION  = "confirm"
    BLOCKED             = "blocked"

@dataclass(frozen=True)
class CapabilityConfig:
    mode: str    # "autonomous" | "confirm" | "draft_only" | "disabled"
```

## Escalation Priority Table

All possible combinations of config mode and session override, resolved in order:

| Config mode   | Session override | Result               | Reason                              |
|---------------|-----------------|----------------------|-------------------------------------|
| `disabled`    | any             | `BLOCKED`            | Hard ceiling, cannot be overridden  |
| `autonomous`  | none            | `EXECUTE`            | No restriction                      |
| `autonomous`  | `confirm`       | `AWAIT_CONFIRMATION` | Session is more restrictive         |
| `confirm`     | none            | `AWAIT_CONFIRMATION` | Default                             |
| `confirm`     | `autonomous`    | `EXECUTE`            | Session escalation allowed          |
| `draft_only`  | none            | `DRAFT`              | Default                             |
| `draft_only`  | `autonomous`    | `DRAFT`              | Ceiling: escalate via YAML only     |
| `draft_only`  | `confirm`       | `DRAFT`              | Session cannot escalate past draft  |

## Configuration (`config/capabilities.yaml`)

```yaml
capabilities:
  calendar:
    enabled: true
    read:    autonomous
    create:  confirm
    update:  confirm
    delete:  confirm
  email:
    enabled: true
    read:    autonomous
    create:  draft_only
    update:  draft_only
    delete:  confirm
  research:
    enabled: true
    read:    autonomous
  workflow:
    enabled: true
    execute: confirm
  companion:
    enabled: true
    reason:  autonomous
```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze.settings` | Path to `capabilities.yaml` |
| `ze.errors` | `CapabilityConfigError` |
| `ze.logging` | Warning log for unknown keys; audit log for decisions |

## Implementation Notes

- `CapabilityGate` is a class. Load config in `__init__`; expose `evaluate()`.

```python
class CapabilityGate:
    def __init__(self, config_path: Path, logger: structlog.BoundLogger): ...

    def evaluate(
        self,
        agent: str,
        intent: str,
        session_overrides: dict[str, str],
    ) -> GateDecision: ...

    def update_permanent(self, agent: str, intent: str, mode: str) -> None: ...

    def _reload(self) -> None: ...  # called on SIGHUP
```

- SIGHUP handler registration belongs in `ze/api/app.py` (the FastAPI lifespan),
  not inside `CapabilityGate` itself.
- Atomic YAML write pattern:

```python
tmp = config_path.with_suffix(".yaml.tmp")
tmp.write_text(yaml.dump(new_config))
tmp.rename(config_path)   # atomic on POSIX systems
```

- Session overrides are stored in `AgentState.session_overrides` (LangGraph state),
  not in process-level globals. The gate receives them as a plain dict argument.
- Log every `BLOCKED` and `AWAIT_CONFIRMATION` decision with `agent`, `intent`,
  `config_mode`, `session_override` (if any), and `session_id`.

## Open Questions

All resolved. (`scope_limit` field removed — will be reconsidered in Phase 3
if a concrete use case emerges.)
