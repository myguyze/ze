# Spec 11 — Ze Persona & Agent Identity

## Problem

Each agent currently defines its own system prompt in full. This produces four different
"voices" — only the companion agent has any personality at all. The research, calendar,
and email agents feel like generic task tools rather than facets of a single assistant.
There is also no way to customise Ze's personality without touching code.

## Goal

1. Give every agent a shared identity block so Ze sounds like the same assistant
   regardless of which agent handles the request.
2. Allow the user to configure Ze's personality via a YAML file (`config/persona.yaml`),
   hot-reloadable without restart.

## Design

### Prompt structure

Every agent's final system prompt is composed of two sections:

```
[IDENTITY BLOCK]
  • Ze's name and role
  • Personality traits (configurable)
  • Verbosity preference (configurable)
  • Custom instructions (configurable)
  • Memory context (what Ze knows about the user)

[AGENT INSTRUCTIONS]
  • Agent-specific behavioural guidelines
  • Operational constraints (e.g. timezone for calendar)
  • No identity or memory content — purely task-level
```

`BaseAgent._build_system_prompt(agent_instructions, ctx, **extra)` composes these two
sections. Each agent passes its own `AGENT_INSTRUCTIONS` template string and any extra
template variables (e.g. `timezone`).

### `config/persona.yaml`

```yaml
# Ze persona configuration.
# Edit to change how Ze presents itself.

traits:
  - direct
  - warm
  - concise

# concise | balanced | detailed
verbosity: concise

# Free-form addition appended after traits, before memory context.
# Leave blank for no custom instruction.
custom_instructions: ""
```

**`traits`** — rendered as a natural-language list ("direct, warm, and concise").
Each item is a single adjective or short phrase.

**`verbosity`** — maps to a behavioural instruction injected after the traits sentence:
- `concise`: "Keep responses brief — one to two paragraphs unless the user asks for more."
- `balanced`: no additional instruction (the default register)
- `detailed`: "Be thorough — elaborate fully and include examples where helpful."

**`custom_instructions`** — free-form text inserted between the verbosity clause and the
memory context. Use for user-specific quirks ("always respond in European Portuguese",
"use my name João", etc.).

### Settings

`Settings.persona_config` — new `@property` that loads `config/persona.yaml`. Returns a
safe default dict if the file is absent so Ze degrades gracefully.

### `ze/agents/identity.py`

Single public function:

```python
def build_identity_block(persona: dict, memory_context: str) -> str: ...
```

Returns the rendered identity block string. Pure function — no I/O, easy to unit-test.

### `ze/agents/base.py`

New method on `BaseAgent`:

```python
def _build_system_prompt(
    self,
    agent_instructions: str,
    ctx: AgentContext,
    **extra: str,
) -> str:
```

Calls `build_identity_block`, then renders `agent_instructions` with any `**extra`
keyword args (e.g. `timezone=...`), and joins the two sections with a blank line.

### Agent instructions

Each agent defines a module-level `_AGENT_INSTRUCTIONS` string constant at the top of
`agent.py` — the agent-specific behavioural section only. No `{memory_context}`
placeholder; that is injected by `_build_system_prompt`. The calendar agent retains
`{timezone}` as a template variable. There is no separate `prompt.py` file.

### Agent files

Each `agent.py` replaces its inline `SYSTEM_PROMPT.format(...)` call with
`self._build_system_prompt(AGENT_INSTRUCTIONS, ctx)` (or with `timezone=...` for
calendar). The `CalendarAgent._system_prompt()` helper is removed.

## Files changed / created

| File | Change |
|---|---|
| `phases/011-persona/spec.md` | New — this spec |
| `config/persona.yaml` | New — default persona config |
| `ze/agents/identity.py` | New — `build_identity_block()` |
| `ze/settings.py` | Add `persona_config` property |
| `ze/agents/base.py` | Add `_build_system_prompt()` |
| `ze/agents/companion/agent.py` | Inline `_AGENT_INSTRUCTIONS`; use `_build_system_prompt()` |
| `ze/agents/research/agent.py` | Inline `_AGENT_INSTRUCTIONS`; use `_build_system_prompt()` |
| `ze/agents/calendar/agent.py` | Inline `_AGENT_INSTRUCTIONS`; use `_build_system_prompt()`; remove `_system_prompt()` |
| `ze/agents/email/agent.py` | Inline `_AGENT_INSTRUCTIONS`; use `_build_system_prompt()` |
| `ze/agents/*/prompt.py` | Deleted — instructions moved inline |

## Out of scope

- Per-agent persona overrides (all agents share one identity block).
- Storing persona as a user fact in the DB (file-based config is simpler and editable).
- Language localisation beyond `custom_instructions`.
