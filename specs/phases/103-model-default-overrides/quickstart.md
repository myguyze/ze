# Quickstart: Model Default with Overrides

Validation guide for the resolver introduced in this feature. Assumes `make dev`
(or `make dev-full`) is already running against a local Postgres (`make db-up`).

## Prerequisites

- Repo checked out on branch `103-model-default-overrides`, implementation applied.
- `apps/ze-api/config/config.yaml` has a `models.default` key set (per
  `data-model.md`).
- Backend running: `make dev` (uvicorn on `:8000`).

## Scenario 1 — Global default swap propagates without a restart (SC-001)

1. With the backend running, send a message to a non-overridden agent (e.g.
   `companion`) via the web app or `POST /api/v0/messages` and note the response.
2. Edit `apps/ze-api/config/config.yaml`: change `models.default` to a different
   valid OpenRouter model id.
3. **Without restarting the backend**, send another message to `companion`.
4. Expected: the second request's trace (`GET /api/v0/messages/{id}/trace` or the
   "Why?" panel) shows the new model, confirming the config change took effect live.

## Scenario 2 — Per-agent override pins a model regardless of the default (SC-002)

1. Add an entry under `models.overrides` in config.yaml for one agent, e.g.
   `overrides: {companion: anthropic/claude-sonnet-4-5}`.
2. Change `models.default` to a different model.
3. Message `companion` — expect the trace to show `anthropic/claude-sonnet-4-5`
   (the override), not the new default.
4. Message a different, non-overridden agent — expect it to show the new default.
5. Remove the override entry, reload — `companion` now follows the default again.

## Scenario 3 — Capability-specific steps are unaffected (SC-003)

1. With `models.default` changed to something other than the transcription/vision
   defaults, send a voice message and an image message.
2. Expected: transcription still uses `models.whisper`'s configured model and
   vision captioning still uses `models.vision_caption`'s configured model —
   check the trace or server logs for the model id used at the
   `preprocess`/`whisper`/`vision_caption` step. Neither should show the new
   `models.default` value.

## Scenario 4 — Fail-fast on missing default (FR-006)

1. Remove `models.default` entirely from config.yaml (or set it to an empty
   string).
2. Restart the backend (`make dev`).
3. Expected: startup fails immediately with an `AgentConfigError` naming
   `models.default` as missing — not a silent fallback, not a per-request failure
   later.
4. Restore `models.default` before continuing.

## Scenario 5 — Fail-fast on an unknown override key (FR-007)

1. Add a typo'd override key to config.yaml, e.g. `overrides: {compnaion: ...}`.
2. Restart the backend.
3. Expected: startup fails with an `AgentConfigError` listing `compnaion` as an
   unrecognized model key.
4. Fix the typo (or remove the entry) before continuing.

## Scenario 6 — Trial model is live by default (SC-004)

1. On a fresh checkout of this feature with no manual config edits, confirm
   `apps/ze-api/config/config.yaml` has `models.default: tencent/hy3:free`.
2. Message any non-overridden agent and confirm the trace shows `tencent/hy3:free`.

## Scenario 7 — Reverting the trial is a one-line edit (SC-005)

1. Change `models.default` back to `anthropic/claude-sonnet-4-5` (or whatever the
   pre-trial default was).
2. Message a non-overridden agent — expect the trace to show the reverted model,
   with no restart and no code change required.

## Automated coverage

Each scenario above has a corresponding unit test:
- Scenarios 1–3, 6–7 → `core/ze-agents/tests/test_model_resolution.py` (resolver
  precedence, capability-key exclusion) plus updated tests at each of the 8
  migrated call sites (`ze-core`, `ze-personal`, `ze-calendar`, `ze-api` test
  suites — see `plan.md` Project Structure).
- Scenarios 4–5 → a startup-validation test for `validate_model_config` (missing
  default, unknown override key).
