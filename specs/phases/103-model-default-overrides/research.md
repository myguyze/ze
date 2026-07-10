# Research: Model Default with Overrides

## 1. How does config.yaml actually reach running code today?

**Decision**: Treat `Settings.config` as already "hot" — no signal handling to build.

**Rationale**: `ZeApiSettings.config` (`apps/ze-api/ze_api/settings.py`) is a
`@property`, not a cached field: every access calls `_load_yaml(config_dir /
"config.yaml")`, which re-reads and re-parses the file from disk. `get_settings()`
itself is `@lru_cache`, but that only caches the `ZeApiSettings` *instance* (which
holds env-derived fields); every `.config` access on that instance re-reads the
YAML file fresh. Grepping the codebase found no `SIGHUP` handler and no
`signal.signal(...)` call anywhere in `apps/` or `core/` — CLAUDE.md's "hot-reloaded
on SIGHUP" phrasing describes the observed effect (edit the file, next call sees
it) but not the actual mechanism. Practical consequence for this feature: no new
reload plumbing is needed — a resolver that reads `config["models"]` on every
invocation already gets live values for free, matching FR-004.

**Alternatives considered**: Adding an explicit SIGHUP handler or file-watcher —
rejected as unnecessary; the existing read-on-every-access behavior already
satisfies "no restart needed," and the feature spec doesn't ask for anything beyond
that.

## 2. Where are model strings actually resolved today, end to end?

**Decision**: Catalogued every general chat-completion call site; found the
resolution logic is duplicated 7 times with inconsistent (and in several cases
dead) config wiring.

**Findings**:

| Call site | File | Declared fallback | Reads from config key | Config.yaml actually defines it under |
|---|---|---|---|---|
| Agent execution (per-turn) | `ze_core/routing/router.py::_resolve_model` | `agent_cls.model` / `agent_cls.model_simple` | *(none — reads class attribute directly)* | n/a |
| Router LLM decomposition fallback | `ze_core/container.py` → `RouterConfig.fallback_model` | `MODEL_ROUTER_FALLBACK` | `routing.fallback_model` | *(not set anywhere — always falls through to the constant; `models.router` in config.yaml is dead, unread by any code)* |
| Multi-agent synthesis | `ze_core/orchestration/nodes/memory.py::synthesize` | `"anthropic/claude-haiku-4-5"` (inline) | `models.synthesis` | `routing.synthesis` **(mismatch — dead)** |
| Session titling | `ze_api/api/websocket/session_titles.py` | `_DEFAULT_MODEL` | `models.session_title` | `models.session_title` (correct — the one call site that isn't broken) |
| Workflow verification/synthesis | `ze_personal/graph/workflow.py::_resolve_verify_model` | `MODEL_WORKFLOW_VERIFY` | `models.workflow_verify` | `routing.workflow_verify` **(mismatch — dead)** |
| Weekly insights generation | `ze_personal/jobs/insights.py` | `"anthropic/claude-haiku-4-5"` (inline) | `models.insights` | `routing.insights` **(mismatch — dead)** |
| Reminder interval assessment | `ze_calendar/reminders/calendar.py::_assess_intervals` | `"anthropic/claude-haiku-4-5"` (inline) | `models.reminders` | `routing.reminders` **(mismatch — dead)** |
| Audio transcription *(capability-specific — out of scope for the default chain)* | `ze_core/orchestration/nodes/preprocessing.py` | `MODEL_WHISPER` | `models.whisper` | `routing.whisper` **(mismatch — dead)** |
| Vision captioning *(capability-specific — out of scope for the default chain)* | `ze_core/orchestration/nodes/preprocessing.py` | `MODEL_VISION_CAPTION` | `models.vision_caption` | `routing.vision_caption` **(mismatch — dead)** |
| Local embedding *(capability-specific — out of scope for the default chain)* | `ze_core/container.py` | n/a | `models.embedding` | `models.embedding` (correct) |

**Rationale for calling this out explicitly**: five of nine call sites read a
`models.*` key that config.yaml has never actually set (it sets the same-named key
one level up, under `routing:`). This means today, editing
`routing.synthesis`/`routing.workflow_verify`/`routing.insights`/`routing.reminders`/
`routing.whisper`/`routing.vision_caption` in config.yaml silently does nothing —
every one of those calls has been running on its hardcoded Python constant the
whole time. Since this feature touches every one of these call sites anyway to wire
them to the shared resolver, fixing the key mismatch is a natural (and necessary —
otherwise the new `models.overrides` map would suffer the same silent-no-op bug)
side effect, not scope creep.

**Alternatives considered**: Leaving the broken `routing.*` keys in place and only
adding the new `models.default`/`models.overrides` keys alongside them — rejected,
because it would leave dead config in the file that looks like it does something
(actively misleading for future maintainers) and would not actually fix the bug
that makes per-step pinning silently fail today.

## 3. Where should the shared resolver live?

**Decision**: `core/ze-agents/ze_agents/model_resolution.py`.

**Rationale**: `ze-agents` is already the lowest common package: `ze-core` depends
on it, and both plugins touched by this change (`ze-personal`, `ze-calendar`)
already import from `ze_agents` directly today (e.g.
`ze_personal/graph/workflow.py` does `from ze_agents.defaults import
MODEL_WORKFLOW_VERIFY`), alongside their `ze-sdk` dependency. Placing the resolver
next to `defaults.py` (the existing home for every `MODEL_*` constant used as a
"declared fallback") and `errors.py` (home of `AgentConfigError`, reused for
fail-fast validation) keeps all three model-related concerns in one package with no
new cross-layer dependency introduced anywhere.

**Alternatives considered**:
- `ze-core` — rejected: plugins cannot depend on `ze-core` (constitution Principle
  III), and two plugin call sites need the resolver.
- `ze-sdk` — considered, since it's the plugin-facing re-export layer; rejected in
  favor of `ze-agents` directly, matching the existing precedent that plugins
  already import `ze_agents.defaults` and `ze_agents.errors` directly rather than
  via a `ze-sdk` re-export. Adding a `ze-sdk` re-export of `resolve_model` is a
  cheap follow-up if a future plugin author finds the direct import surprising, but
  isn't required to satisfy any functional requirement here.

## 4. How should unknown/missing config be detected (FR-006, FR-007)?

**Decision**: One `validate_model_config(config: dict, known_keys: frozenset[str])`
function in `model_resolution.py`, called once during container/app startup
(`ze_core/container.py`, alongside the existing `RouterConfig` wiring). It:
1. Raises `AgentConfigError` if `config["models"]["default"]` is missing or empty.
2. Raises `AgentConfigError` listing every override key in
   `config["models"]["overrides"]` that isn't in `known_keys` (the union of
   registered agent names from `get_enabled_agents()` and the static
   `KNOWN_STEP_KEYS` set for non-agent call sites: `router_fallback`, `synthesis`,
   `session_title`, `workflow_verify`, `insights`, `reminders`).

**Rationale**: `AgentConfigError` (subclass of `AgentError` → `ZeCoreError`) already
exists for exactly this class of problem ("agent-related configuration is
malformed") — no new error type needed, consistent with the "raise a typed
`ZeError` subclass" convention. Startup-time validation (rather than per-request)
means a bad config fails loudly once, immediately, rather than causing confusing
per-agent failures later; this matches how `RouterConfig` and other startup wiring
already fail fast in `container.py` today.

**Alternatives considered**: Validating lazily on first resolution per key —
rejected, because a typo'd override for a rarely-hit step (e.g. `insights`, which
only runs weekly) could silently sit broken for days before anyone notices; failing
at startup surfaces it immediately.

## 5. Does `models.overrides` interact with the existing `model_simple` (complexity-based) variant?

**Decision**: An override, when present for an agent, wins outright and bypasses
the `model_simple`/`model` complexity split entirely. `model_simple` continues to
apply only when there is no override for that agent.

**Rationale**: The spec's resolution order (override → declared → default) doesn't
mention a fourth complexity-based tier, and introducing one would silently
complicate the mental model this feature exists to simplify ("one line to try a
model everywhere"). Treating `model_simple` as part of the "declared" tier (i.e.,
still resolved by the agent's own class-attribute logic when no override exists)
keeps that existing, unrelated feature intact without expanding this feature's
scope.

**Alternatives considered**: A separate `overrides_simple` map for the
complexity-reduced variant — rejected as unrequested complexity; nothing in the
spec calls for overriding the simple-complexity path independently, and it can be
added later if a real need shows up.
