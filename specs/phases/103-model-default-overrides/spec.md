# Feature Specification: Model Default with Overrides

**Feature Branch**: `103-model-default-overrides`

**Created**: 2026-07-10

**Status**: Implemented

**Input**: User description: "Model default with overrides — Right now every agent hardcodes its LLM as a `model = \"...\"` class attribute, and support/routing models are scattered as individual keys under `routing:` in config.yaml. There's no single place to say \"use this model everywhere unless told otherwise,\" so trying out a different model (e.g. to evaluate a new free/cheap model on OpenRouter) means hand-editing many files. Add a `models.default` fallback in config.yaml plus a `models.overrides: {agent_name: model_id}` map, with resolution order: override → agent's declared model attribute → global default. config.yaml already hot-reloads on SIGHUP so swapping the default becomes a one-line edit, no restart, no code changes. Capability-specific models that aren't general chat completions (whisper/audio transcription, vision_caption/multimodal captioning, embedding) should stay pinned and excluded from the default-fallback chain since they need specific capabilities, not \"whatever the default happens to be.\" As part of this change, set `models.default` to `tencent/hy3:free` (a free OpenRouter model) so we can trial it through 2026-07-21 with an easy one-line revert afterward."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trial a new model across the whole assistant with one edit (Priority: P1)

The maintainer wants to evaluate a new LLM (e.g. a newly released free model on OpenRouter) across all of Ze's conversational agents and routing/support steps, without editing every agent file individually and without restarting the running service.

**Why this priority**: This is the core friction the feature exists to remove. Without it, every model trial costs a multi-file edit + code deploy, which discourages experimentation entirely.

**Independent Test**: Can be fully tested by changing a single value in the running configuration and observing, without a restart, that agents and routing/support steps which don't have an explicit override now use the new model for their next request.

**Acceptance Scenarios**:

1. **Given** Ze is running with its current default model, **When** the maintainer changes only the global default value in configuration and reloads config, **Then** every agent and routing/support step that has no explicit override uses the new model on its next invocation.
2. **Given** the global default has just been changed, **When** the maintainer reverts the value to the previous model and reloads config, **Then** all affected agents and steps return to the previous model with no other changes required.

---

### User Story 2 - Pin a specific agent to a specific model (Priority: P2)

The maintainer wants most agents to follow the global default, but needs one particular agent (e.g. one that consistently needs a stronger reasoning model, or one under active comparison) to keep using a specific model regardless of what the global default is set to.

**Why this priority**: Overrides are what make the default safe to change fleet-wide — without them, changing the default is an all-or-nothing action, which reintroduces the original friction for anyone who needs an exception.

**Independent Test**: Can be tested by setting an override for one named agent while leaving the global default at a different value, then confirming that agent alone uses the overridden model while every other agent uses the default.

**Acceptance Scenarios**:

1. **Given** an override is configured for a specific agent, **When** that agent runs, **Then** it uses the overridden model even though the global default is set to a different model.
2. **Given** an override is configured for a specific agent, **When** the global default is changed, **Then** the overridden agent's model is unaffected while all other agents follow the new default.
3. **Given** an override was previously set for an agent, **When** the override is removed from configuration and config is reloaded, **Then** that agent falls back to the agent's own declared model, or the global default if it has none.

---

### User Story 3 - Capability-specific steps are never silently swapped (Priority: P2)

The maintainer changes the global default model to trial a new general-purpose chat model, and needs steps that depend on a specific capability (audio transcription, image/vision captioning, text embedding) to keep working exactly as before, since those steps require a model with that specific capability rather than "whatever the default currently is."

**Why this priority**: A capability-specific step silently picking up a default model that can't actually perform that capability (e.g. a text-only free model swapped in for audio transcription) would break functionality in a way that's easy to miss and directly undermines trust in the "safe to change the default" promise from User Story 1.

**Independent Test**: Can be tested by changing the global default and confirming that audio transcription, vision captioning, and embedding continue to use their previously configured models, unaffected by the default change.

**Acceptance Scenarios**:

1. **Given** the global default model is changed, **When** an audio transcription, vision captioning, or embedding step runs, **Then** it continues to use its own explicitly configured model, not the new default.

---

### Edge Cases

- What happens when the global default is left unset entirely? System must fail fast at startup with a clear error rather than silently leaving some agents without any resolvable model.
- What happens when an override references an agent name that doesn't exist (e.g. a typo)? The system should surface this misconfiguration rather than silently ignoring it, so mistakes are caught before they mask a working override.
- What happens when both an agent's own declared model and an override exist for the same agent? The override takes precedence, per the resolution order (override → agent's declared model → global default).
- What happens mid-request, if the model is changed while an agent's current turn is in flight? The in-flight turn completes with the model that was resolved when it started; only subsequent turns pick up the new value.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a single global default model setting that applies to any agent or routing/support step that does not have a more specific model configured.
- **FR-002**: System MUST provide a way to configure a model override for an individual named agent or routing/support step, which takes precedence over both that agent's own declared model and the global default.
- **FR-003**: System MUST resolve the effective model for each agent/step in this order: explicit override, then the agent's own declared model (if any), then the global default.
- **FR-004**: System MUST allow the global default and all overrides to be changed without restarting the running service, consistent with the existing configuration hot-reload behavior.
- **FR-005**: System MUST exclude capability-specific models (audio transcription, vision/image captioning, text embedding) from the default-fallback chain — these always use their own explicitly configured model and are never silently replaced by the global default.
- **FR-006**: System MUST fail with a clear, actionable error at startup (or at config reload) if no global default model is configured.
- **FR-007**: System MUST detect and surface an override entry that references an agent or step name unknown to the system, rather than silently ignoring it.
- **FR-008**: System MUST set the global default model to `tencent/hy3:free` as part of this change, so it is the effective model for every agent and routing/support step that lacks its own override, until it is manually changed back.
- **FR-009**: Documentation describing how to configure models MUST be updated to describe the default/override resolution order and how to add or remove an override, so future model trials don't require re-deriving this behavior from code.

### Key Entities

- **Global default model**: The single fallback model identifier used by any agent or step that has no more specific model configured.
- **Model override**: A named agent-or-step to model-identifier mapping that takes precedence over both the global default and that agent's own declared model.
- **Capability-specific model**: A model identifier tied to a step that depends on a specific capability (transcription, vision, embedding) rather than general chat completion; always configured explicitly and never affected by the global default.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can change the effective model for every general-purpose agent and routing/support step in the system by editing exactly one configuration value, with no code changes and no service restart.
- **SC-002**: A maintainer can pin an individual agent to a specific model, independent of the global default, by adding a single configuration entry.
- **SC-003**: After the global default model is changed, capability-specific steps (transcription, vision captioning, embedding) continue producing correct results using their own pinned models, with zero regressions.
- **SC-004**: Immediately after this change ships, the assistant is running on `tencent/hy3:free` as its effective default model for all non-overridden, non-capability-specific agents and steps.
- **SC-005**: Reverting the trial model back to the prior default is a single configuration edit, completed in under a minute, with no code changes.

## Assumptions

- "Agents and routing/support steps" refers to every place in the system that currently has either a `model = "..."` class attribute on an agent or a model entry under the `routing:` section of configuration — i.e., every general-purpose chat-completion call site.
- The existing configuration hot-reload mechanism (SIGHUP) is trusted as-is for propagating both the global default and override changes; this feature does not need to introduce a new reload mechanism.
- "Capability-specific" is limited, for this feature, to audio transcription, vision/image captioning, and text embedding — the three non-chat-completion model uses identified in the current system. Any future capability-specific model added later is expected to follow the same exclusion pattern.
- The `tencent/hy3:free` trial is a configuration-value choice, not a code change — once the default/override mechanism exists, setting and later reverting the trial model is just editing the default value.
- The 2026-07-21 trial end date is a reminder for the maintainer to manually revert the default; this feature does not need to build an automatic time-based expiry mechanism.
