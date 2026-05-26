# Ze Core — Capability Gate — Spec

## Purpose

Authorise or restrict agent actions based on per-agent, per-intent permission
modes declared in the agent class. The gate is the sole enforcement point for
Ze Core's permission model — no agent checks permissions itself.

This spec supersedes Ze's `02-capability-gate.md` for the Ze Core implementation.
The key difference: capability modes are declared as class attributes on the
`@agent` class, not loaded from a YAML file. There is no `update_permanent()`.
There is no SIGHUP reload. Modes are source code, changed by editing the agent
class and redeploying.

## Responsibilities

- Evaluate `(agent, intent)` pairs against the mode declared on the agent class.
- Apply per-session temporary overrides (escalation and restriction).
- Enforce the escalation ceiling: session overrides cannot elevate `draft_only`
  to `execute`. Only a code change can do that.
- Return a `GateDecision` for every evaluation.

## Out of Scope

- Does not load any configuration file.
- Does not write to any file or database.
- Does not select which tool to call.
- Does not execute tools.
- Does not send confirmation messages to the user (that is `AppInterface`'s job
  via the `await_confirmation` orchestration node).
- Does not persist session overrides (the caller owns the `session_overrides` dict).

---

## Interface Contract

### Input

```python
agent: str                        # e.g. "calendar" — must match a registered agent name
intent: str                       # e.g. "create"
session_overrides: dict[str, str] # "agent.intent" → mode string, e.g. {"calendar.create": "autonomous"}
```

### Output

```python
GateDecision  # EXECUTE | DRAFT | AWAIT_CONFIRMATION | BLOCKED
```

### Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| Agent not in registry | Return `AWAIT_CONFIRMATION`, log warning |
| Agent has `enabled = False` | Return `BLOCKED` immediately, skip intent check |
| Intent not in `capabilities` dict | Default to `AWAIT_CONFIRMATION`, log warning |
| `Mode.DISABLED` for intent | Return `BLOCKED` — cannot be overridden by session |
| Session tries to escalate past `draft_only` | `DRAFT` — ceiling enforced |
| Unknown session override mode string | Treat as no override, log warning |

---

## Data Structures

`ze_core/capability/types.py`

```python
class GateDecision(Enum):
    EXECUTE            = "execute"
    DRAFT              = "draft"
    AWAIT_CONFIRMATION = "confirm"
    BLOCKED            = "blocked"

class Mode(str, Enum):
    AUTONOMOUS = "autonomous"   # → EXECUTE
    CONFIRM    = "confirm"      # → AWAIT_CONFIRMATION
    DRAFT_ONLY = "draft_only"   # → DRAFT
    DISABLED   = "disabled"     # → BLOCKED
```

---

## Mode → Decision Mapping

| Agent class `capabilities[intent]` | Base decision |
|---|---|
| `Mode.AUTONOMOUS` | `EXECUTE` |
| `Mode.CONFIRM` | `AWAIT_CONFIRMATION` |
| `Mode.DRAFT_ONLY` | `DRAFT` |
| `Mode.DISABLED` | `BLOCKED` |

---

## Escalation Ceiling Table

Session overrides can escalate or restrict within the ceiling set by the agent class.
`DISABLED` and `DRAFT_ONLY` are hard ceilings — session cannot escalate past them.

| Agent class mode | Session override | Result | Reason |
|---|---|---|---|
| `DISABLED` | any | `BLOCKED` | Hard ceiling |
| `AUTONOMOUS` | none | `EXECUTE` | No override |
| `AUTONOMOUS` | `confirm` | `AWAIT_CONFIRMATION` | Session restricts |
| `AUTONOMOUS` | `draft_only` | `DRAFT` | Session restricts further |
| `CONFIRM` | none | `AWAIT_CONFIRMATION` | No override |
| `CONFIRM` | `autonomous` | `EXECUTE` | Session escalates (allowed — ceiling is EXECUTE) |
| `CONFIRM` | `draft_only` | `DRAFT` | Session restricts |
| `DRAFT_ONLY` | none | `DRAFT` | No override |
| `DRAFT_ONLY` | `autonomous` | `DRAFT` | Ceiling blocks escalation |
| `DRAFT_ONLY` | `confirm` | `DRAFT` | Ceiling blocks escalation |

---

## Implementation

`ze_core/capability/gate.py`

```python
class CapabilityGate:
    def evaluate(
        self,
        agent: str,
        intent: str,
        session_overrides: dict[str, str],
    ) -> GateDecision:
        from ze_core.orchestration.registry import get_agent_class
        from ze_core.errors import UnknownAgentError

        try:
            agent_cls = get_agent_class(agent)
        except UnknownAgentError:
            log.warning("capability_unknown_agent", agent=agent)
            return GateDecision.AWAIT_CONFIRMATION

        if not agent_cls.enabled:
            return GateDecision.BLOCKED

        mode: Mode | None = agent_cls.capabilities.get(intent)
        if mode is None:
            log.warning("capability_unknown_intent", agent=agent, intent=intent)
            return GateDecision.AWAIT_CONFIRMATION

        if mode == Mode.DISABLED:
            return GateDecision.BLOCKED

        base = _MODE_TO_DECISION[mode]
        ceiling = _MODE_CEILING[mode]

        override_str = session_overrides.get(f"{agent}.{intent}")
        if override_str is None:
            return base

        try:
            override_mode = Mode(override_str)
        except ValueError:
            log.warning("capability_unknown_override_mode", mode=override_str)
            return base

        requested = _MODE_TO_DECISION[override_mode]
        return requested if _at_or_below_ceiling(ceiling, requested) else ceiling
```

`CapabilityGate` has no constructor arguments. It reads directly from the agent
registry, which is populated at import time by `@agent`. No config file. No path.
No startup loading step.

---

## Session Overrides

Session overrides are temporary, per-invocation capability adjustments. They are
passed to `gate.evaluate()` as a plain `dict[str, str]` and do not persist beyond
the current graph invocation.

The key format is `"agent.intent"`. The value is a mode string
(`"autonomous"`, `"confirm"`, `"draft_only"`). `"disabled"` is not a valid override
value — you cannot disable an agent at session level.

**Where overrides come from** is application-specific. Ze uses them via:
- A Telegram command that sets overrides for the current session.
- The REST API `AgentState` that can be seeded with overrides at invocation time.

Ze Core does not define how overrides are set — only how they are applied.

---

## What Replaced `update_permanent()`

Ze's previous gate had `update_permanent()` which rewrote `config.yaml` at runtime.
This is gone. Capability modes are source code. To change them permanently:

1. Edit the agent's `capabilities` dict in `agent.py`.
2. Commit and redeploy.

For non-permanent per-session changes, use session overrides (see above).

The `PUT /capabilities/{agent}/{intent}` REST endpoint is removed. The
`GET /capabilities` endpoint remains and reads from the agent registry:

```python
GET /capabilities
→ {
    "calendar": {"enabled": true, "read": "autonomous", "create": "confirm", ...},
    "email":    {"enabled": true, "read": "autonomous", "create": "draft_only", ...},
    ...
  }
```

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.orchestration.registry` | `get_agent_class()` — reads `enabled` and `capabilities` |
| `ze_core.capability.types` | `Mode`, `GateDecision` |
| `ze_core.errors` | `UnknownAgentError` |
| `ze_core.logging` | Structured logging for unknown agents / intents |

---

## Usage in the Orchestration Graph

The gate is called in the `capability_check` node:

```python
async def capability_check(state: AgentState, config: RunnableConfig) -> dict:
    gate: CapabilityGate = config["configurable"]["capability_gate"]
    primary = state["envelope"].subtasks[0]
    decision = gate.evaluate(
        agent=primary.agent,
        intent=primary.intent,
        session_overrides=state.get("session_overrides", {}),
    )
    return {"gate_decision": decision}
```

The gate instance is constructed once in the container and injected into the graph
via `config["configurable"]`. It is stateless — safe to share across concurrent
graph invocations.
