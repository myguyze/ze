# Data Model: Model Default with Overrides

This feature has no persisted database entities — no migration, no new table. The
"data model" here is the configuration schema (`config/config.yaml`) and the
resolver's in-memory contract.

## `models` config schema (`apps/ze-api/config/config.yaml`)

```yaml
models:
  default: tencent/hy3:free      # REQUIRED — global fallback for every resolvable key
  overrides:                     # OPTIONAL — empty by default
    <key>: <model_id>            # pins one agent/step to a specific model, bypassing default
  embedding: intfloat/multilingual-e5-base   # capability-specific — never resolved via the chain
  whisper: openai/gpt-audio                   # capability-specific — never resolved via the chain
  vision_caption: google/gemini-flash-1.5      # capability-specific — never resolved via the chain
```

- **`models.default`** (`str`, required): the effective model for any resolvable
  key with no override. Startup fails (`AgentConfigError`) if absent or empty
  (FR-006).
- **`models.overrides`** (`dict[str, str]`, optional, default `{}`): maps a
  resolvable key to a model id that takes precedence over both that key's declared
  default and `models.default`. Startup fails (`AgentConfigError`) if any key isn't
  a known resolvable key (FR-007).
- **`models.embedding` / `models.whisper` / `models.vision_caption`**
  (`str`, each independently optional with an existing Python constant fallback):
  capability-specific model pins, entirely outside the default/override resolution
  chain (FR-005). Unchanged by this feature except that the dead
  `routing.whisper`/`routing.vision_caption` duplicate keys are removed.

## Resolvable keys ("Model Key" entity)

A **Model Key** is a string identifying one resolvable model slot. There are two
kinds:

- **Agent keys** — every `name` in the live `@agent` registry
  (`ze_agents.registry.get_enabled_agents()`), e.g. `companion`, `research`,
  `calendar`, `reminders`, `workflow`, `goals`, `prospecting`, `messenger`, `news`,
  `finance`. Declared default = that agent class's own `model` class attribute.
- **Step keys** — the fixed set `KNOWN_STEP_KEYS` in
  `ze_agents.model_resolution`, one per non-agent chat-completion call site:
  `router_fallback`, `synthesis`, `session_title`, `workflow_verify`, `insights`,
  `reminders`. Declared default = the existing `MODEL_*` constant in
  `ze_agents/defaults.py` for that call site.

  > Note: the step key `reminders` (calendar reminder interval assessment) and the
  > agent key `reminders` (`RemindersAgent`) are namespaced separately in code
  > (different call sites, different `resolve_model()` invocations) but share the
  > same string today. `validate_model_config` treats the combined key set as a
  > single flat namespace, so an override under `models.overrides.reminders`
  > applies to both the reminders agent's per-turn model *and* the reminder
  > interval assessor unless/until they're split into distinct keys. Called out here
  > as a known limitation, not fixed by this feature — both call sites reasonably
  > want the same trial behavior by default, and a future spec can split them if
  > that assumption ever proves wrong.

## Resolution contract (`ze_agents.model_resolution`)

```python
def resolve_model(key: str, declared: str | None, config: dict) -> str:
    """override → declared → default. Raises AgentConfigError if no default configured."""

def validate_model_config(config: dict, known_keys: frozenset[str]) -> None:
    """Raises AgentConfigError if models.default is missing, or if any
    models.overrides key is not in known_keys."""
```

- **Input**: `key` (a Model Key, see above), `declared` (the call site's own
  class-attribute or constant value, may be `None` only for call sites with no
  meaningful declared default), `config` (the live `Settings.config` dict, re-read
  from disk on every access — see research.md §1).
- **Output**: a model id string ready to pass to `LLMClient.complete`/`stream`.
- **Failure mode**: `AgentConfigError` (existing typed error), raised at startup via
  `validate_model_config`, not per-call — by the time `resolve_model` runs during a
  request, the config is already known-valid.
