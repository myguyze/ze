# Spec 25 — Persona Profiles & Dials

## Problem

Ze's personality is a flat, static YAML list — three adjective traits and a verbosity
setting. This makes it awkward to change Ze's character: you must edit a file, issue a
SIGHUP, and the change is all-or-nothing. There is no way to switch between distinct
"modes" (focused/playful/formal), and there are no meaningful behavioural knobs beyond
the trait words themselves.

## Goal

1. Define named persona **profiles** in `config/config.yaml` — each a self-contained
   personality preset with traits, verbosity, and a set of numeric **dials**.
2. Dials are continuous 0–1 values that translate into prose instructions injected into
   the identity block (the TARS-dial model: the number is a UI artefact, the model sees
   English sentences).
3. Persist the active profile choice and any per-session dial overrides in the DB so
   the persona survives process restarts and hot-reloads without re-editing YAML.
4. Expose a `/persona` Telegram command for live switching.

Zero per-agent changes: every agent already calls `_build_system_prompt` → the
identity block update propagates everywhere.

---

## Design

### Config schema

`config/config.yaml` — extend the `persona:` section:

```yaml
persona:
  # Active profile name (DB value takes precedence at runtime).
  profile: default

  profiles:
    default:
      traits: [direct, warm, concise]
      verbosity: concise   # concise | balanced | detailed
      custom_instructions: ""
      dials:
        humor:       0.3   # 0 = none  → 1 = freely witty
        directness:  0.9   # 0 = Socratic → 1 = blunt conclusions-first
        formality:   0.2   # 0 = casual → 1 = formal
        depth:       0.5   # 0 = surface → 1 = full elaboration

    stoic:
      traits: [precise, measured]
      verbosity: concise
      custom_instructions: ""
      dials:
        humor:       0.05
        directness:  1.0
        formality:   0.7
        depth:       0.4

    playful:
      traits: [warm, curious, witty]
      verbosity: balanced
      custom_instructions: ""
      dials:
        humor:       0.85
        directness:  0.4
        formality:   0.1
        depth:       0.6
```

**Backwards compatibility:** if `profiles:` is absent, `settings.py` wraps the legacy
flat `persona:` block as a single `default` profile. No migration needed for YAML.

The four built-in dials shipped with every profile are described in the Dial system
section. Additional dial keys are valid but have no effect until `identity.py` maps them.

---

### Dial system

Each dial maps a continuous `[0.0, 1.0]` float to a prose clause appended after the
traits + verbosity sentence in the identity block. Clauses are only emitted for values
outside the neutral band `[0.2, 0.8)` — within that band the dial is silent, preventing
prompt bloat when the user has not tuned dials deliberately.

| Dial | Low (< 0.2) | High (≥ 0.8) |
|---|---|---|
| `humor` | "Keep responses strictly professional — no humor." | "Wit is central to how you communicate — be openly funny." |
| `directness` | "Explore topics Socratically — show your reasoning, ask questions before concluding." | "State your conclusion first, always. No preamble, no hedging." |
| `formality` | "Use casual language — first names, contractions, conversational tone." | "Formal and precise throughout — avoid contractions and colloquialisms." |
| `depth` | "Keep answers at the surface level — one to two sentences unless asked." | "Go deep — full elaboration with edge cases, examples, and alternatives." |

Values in the `[0.2, 0.5)` and `[0.5, 0.8)` bands produce no clause — the neutral
register is the default and needs no instruction. Only the extremes are explicit.

This keeps the system prompt compact: at default dial values most clauses are silent,
and the traits sentence alone governs behaviour.

---

### `ze/persona/` — new package

```
ze/persona/
├── __init__.py
├── store.py    # PersonaStore — DB reads/writes
└── types.py    # PersonaState dataclass
```

#### `types.py`

```python
@dataclass
class PersonaState:
    profile: str             # active profile name
    dials: dict[str, float]  # dial overrides on top of the profile defaults
    updated_at: datetime
```

#### `store.py`

```python
class PersonaStore:
    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None: ...

    async def get_active(self) -> dict:
        """Return the active profile dict with DB dial overrides merged in."""

    async def set_profile(self, name: str) -> None:
        """Switch profile; clears dial overrides (overrides are profile-relative)."""

    async def set_dial(self, name: str, value: float) -> None:
        """Override one dial on the current profile."""

    async def reset_dials(self) -> None:
        """Restore all dials to the YAML profile defaults."""

    def available_profiles(self) -> list[str]:
        """Names of all profiles defined in YAML."""
```

`get_active` resolution order:
1. Fetch `(profile, dials)` from `persona_state` table (single row, id = 1).
2. Resolve profile dict from YAML (`settings.persona_config["profiles"][profile]`).
3. Merge DB `dials` over profile defaults: `{**profile_dials, **db_dials}`.
4. Return merged dict.

If the DB row is absent (first boot, before migration runs) fall back to
`settings.persona_config["profiles"]["default"]`.

---

### DB migration `012_persona_state.py`

```sql
CREATE TABLE persona_state (
    id         SMALLINT PRIMARY KEY DEFAULT 1
               CONSTRAINT single_row CHECK (id = 1),
    profile    TEXT        NOT NULL DEFAULT 'default',
    dials      JSONB       NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO persona_state (id) VALUES (1) ON CONFLICT DO NOTHING;
```

The `CHECK (id = 1)` constraint enforces the single-row invariant at the DB level.
`dials` stores only overrides (keys that differ from the profile's YAML defaults).
Switching profiles always resets `dials` to `{}` so stale overrides do not bleed across.

---

### `AgentContext` enrichment

`ze/agents/types.py` — add one field:

```python
@dataclass
class AgentContext:
    ...
    persona: dict = field(default_factory=dict)
```

Empty default so existing tests and callers outside the graph do not break.

---

### `ze/orchestration/nodes/context.py`

`fetch_context` resolves the active persona once per graph invocation and stores it on
the context, following the same pattern as `memory_context`:

```python
persona_store: PersonaStore = config["configurable"]["persona_store"]
active_persona = await persona_store.get_active()

agent_context = AgentContext(
    ...
    persona=active_persona,
)
```

---

### `ze/agents/base.py`

`_build_system_prompt` reads `ctx.persona` instead of `self._settings.persona_config`:

```python
def _build_system_prompt(self, agent_instructions, ctx, **extra):
    identity = build_identity_block(
        ctx.persona if ctx.persona else self._settings.persona_config,
        self._format_memory(ctx),
        profile=ctx.memory.profile,
    )
    ...
```

The `self._settings.persona_config` fallback keeps unit tests and any direct agent
invocations outside the graph working without change.

---

### `ze/agents/identity.py`

Add dial rendering. `build_identity_block` accepts the same `persona: dict` parameter;
the dict may now contain a `dials` sub-dict.

New internals:

```python
_DIAL_CLAUSES: dict[str, dict[tuple[float, float], str]] = {
    "humor": {
        (0.0, 0.2): "Keep responses strictly professional — no humor.",
        (0.8, 1.0): "Wit is central to how you communicate — be openly funny.",
    },
    "directness": {
        (0.0, 0.2): "Explore topics Socratically — show reasoning, ask questions before concluding.",
        (0.8, 1.0): "State your conclusion first, always. No preamble, no hedging.",
    },
    "formality": {
        (0.0, 0.2): "Use casual language — first names, contractions, conversational tone.",
        (0.8, 1.0): "Formal and precise throughout — avoid contractions and colloquialisms.",
    },
    "depth": {
        (0.0, 0.2): "Keep answers at the surface level — one to two sentences unless asked.",
        (0.8, 1.0): "Go deep — full elaboration with edge cases, examples, and alternatives.",
    },
}

def _render_dial_clauses(dials: dict[str, float]) -> str:
    clauses = []
    for name, bands in _DIAL_CLAUSES.items():
        value = dials.get(name)
        if value is None:
            continue
        for (lo, hi), clause in bands.items():
            if lo <= value < hi or (hi == 1.0 and value == 1.0):
                clauses.append(clause)
                break
    return " ".join(clauses)
```

`build_identity_block` appends the dial clause string (if non-empty) after the
verbosity clause and before `custom_instructions`.

The identity template gains a `{dial_block}` slot between the verbosity clause and the
custom instructions block:

```
You are Ze, a personal AI assistant. You are {traits}.{verbosity_clause}{dial_block}
...
{custom_block}
```

---

### `settings.py` — `persona_config` property

`persona_config` returns the full `persona:` dict from YAML (unchanged). The new
`profiles:` sub-key is now present when configured. The `PersonaStore` reads this dict;
callers that accessed `settings.persona_config` directly for the flat format continue
to work via the fallback in `BaseAgent._build_system_prompt`.

---

### Telegram `/persona` command

#### Display

```
Ze persona — active: default

Humor        ▓▓▓░░░░░░░  0.3
Directness   ▓▓▓▓▓▓▓▓▓░  0.9
Formality    ▓▓░░░░░░░░  0.2
Depth        ▓▓▓▓▓░░░░░  0.5

[default ✓]  [stoic]  [playful]

Adjust a dial: /persona humor 0.8
Reset dials:   /persona reset
```

The inline keyboard has one row of profile-switching buttons; the active profile shows
a checkmark. Dial tuning uses text commands — it avoids the combinatorial button
explosion of per-dial increment/decrement rows.

#### Command grammar

```
/persona                     → show current state (text + inline keyboard)
/persona <profile>           → switch to named profile, reset dial overrides
/persona <dial> <0.0–1.0>    → set one dial on the active profile
/persona reset               → reset all dial overrides to profile defaults
```

Examples:
```
/persona stoic
/persona humor 0.05
/persona directness 1.0
/persona reset
```

Parsing is strict: unknown profile name → error message listing available profiles;
dial value outside [0.0, 1.0] → error message; unknown dial name → error message.

#### Callback data format

Profile switch buttons carry `persona:profile:<name>` (≤ 64 bytes for any reasonable
profile name). Tap → `handle_callback` dispatches to `_handle_persona_callback`, which
calls `persona_store.set_profile(name)` and re-renders the persona message.

---

### `ze/telegram/commands.py`

New function:

```python
async def persona_summary(pool: asyncpg.Pool, settings: Settings) -> tuple[str, InlineKeyboardMarkup]:
    """Return (formatted text, profile-switch keyboard) for /persona."""
```

Returns a 2-tuple so `bot.py` can pass `reply_markup=` to `send_message`.

---

### `ze/telegram/bot.py`

Three additions to `handle_message`:

```python
if text == "/persona" or text.startswith("/persona "):
    await self._handle_persona_command(chat_id, text)
    return
```

`_handle_persona_command` parses the command, dispatches to `PersonaStore`, and sends
the updated summary.

`handle_callback` gains a branch before the `confirm:` check:

```python
if data.startswith("persona:"):
    await self._handle_persona_callback(chat_id, data, query.id)
    return
```

`_handle_persona_callback` calls `persona_store.set_profile(name)`, edits the existing
message with the updated summary (rather than sending a new one), and answers the
callback query.

`ZeBot` gains a `persona_store: PersonaStore` constructor parameter.

---

### `ze/container.py`

1. Construct `PersonaStore(pool=pool, settings=settings)`.
2. Add `persona_store=persona_store` to the `graph_config["configurable"]` dict
   (alongside `memory_store`, `embedder`, `settings`).
3. Pass `persona_store=persona_store` when constructing `ZeBot`.

---

## Files changed / created

| File | Change |
|---|---|
| `specs/25-persona-profiles.md` | New — this spec |
| `config/config.yaml` | Extend `persona:` with `profile:` and `profiles:` map |
| `ze/persona/__init__.py` | New — empty |
| `ze/persona/types.py` | New — `PersonaState` dataclass |
| `ze/persona/store.py` | New — `PersonaStore` |
| `migrations/versions/012_persona_state.py` | New — `persona_state` table |
| `ze/agents/types.py` | Add `persona: dict` field to `AgentContext` |
| `ze/agents/identity.py` | Add `_DIAL_CLAUSES`, `_render_dial_clauses`, update `build_identity_block` |
| `ze/agents/base.py` | `_build_system_prompt` reads `ctx.persona` |
| `ze/orchestration/nodes/context.py` | Resolve active persona; set on `agent_context` |
| `ze/telegram/commands.py` | Add `persona_summary()` |
| `ze/telegram/bot.py` | Add `/persona` command handler + persona callback handler |
| `ze/container.py` | Wire `PersonaStore`; add to graph config and `ZeBot` |
| `tests/persona/test_store.py` | New — unit tests for `PersonaStore` |
| `tests/agents/test_identity.py` | Extend — dial rendering coverage |
| `tests/telegram/test_commands.py` | Extend — `persona_summary` tests |

---

## Out of scope

- Per-agent dial overrides (all agents share one active persona).
- Per-conversation ephemeral persona (profile persists across sessions by design).
- Exporting / importing profiles via Telegram.
- Fine-grained per-dial increment buttons in the inline keyboard (text commands cover
  this; button matrix is disproportionate complexity for the single-user case).
- More than four dials in the first version; the design is additive.
