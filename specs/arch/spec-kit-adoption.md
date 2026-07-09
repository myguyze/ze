# ADR: Adopt GitHub spec-kit for feature spec workflow

> **Status:** Accepted
> **Date:** 2026-07-09
> **Implemented in:** Spec workspace migration (this ADR's commit)
> **Scope:** `specs/`, `.specify/`, `.claude/skills/`, all docs referencing spec paths

---

## Context and Problem Statement

Ze has had a spec-first culture since day one, but the spec workspace was a flat,
single-file-per-phase convention: `specs/phases/N-name.md` holding everything from
goals to data model to rollout. As phases grew (100+ specs), single files became
overloaded — research notes, API contracts, task breakdowns, and pre-mortems either
crowded the spec or were never written at all. There was no formal pipeline between
"spec written" and "code written": no clarify stage to de-risk ambiguity, no task
derivation, no cross-artifact consistency check. Open Questions sections were the
only clarify mechanism, and they routinely went stale.

GitHub spec-kit provides exactly this pipeline: a `specify` CLI plus agent skills
(`/speckit-specify`, `-clarify`, `-plan`, `-tasks`, `-analyze`, `-implement`,
`-checklist`, `-constitution`) that generate one directory per feature
(`NNN-name/{spec,plan,research,data-model,tasks}.md` + `contracts/`) governed by a
project constitution in `.specify/memory/constitution.md`. It has no equivalent for
Ze's `specs/core/` (per-package infrastructure specs) or `specs/arch/` (ADRs).

---

## Decision Drivers

- Keep Ze's three-category organisation (`phases/`, `core/`, `arch/`) — spec-kit only
  replaces the *feature* spec format, not the whole workspace.
- Preserve phase numbering continuity (next feature is 102) and git history of
  existing specs.
- The spec→plan→tasks→implement pipeline with a constitution gate is the feature
  being bought; templates alone would not justify a migration.
- Single maintainer + Claude Code as the primary implementer — agent-native skills
  matter more than human ceremony.

---

## Considered Options

1. **Adopt spec-kit fully, migrate existing specs** — install scaffolding, convert
   every `phases/N-name.md` to `phases/NNN-name/spec.md`, point spec-kit at
   `specs/phases/`.
2. **Adopt spec-kit for new specs only** — leave the 100 flat files as legacy;
   new features get directories.
3. **Cherry-pick templates only** — copy spec/plan/tasks templates into Ze's own
   convention without the CLI, skills, or constitution.

---

## Decision Outcome

**Chosen option: Option 1 — full adoption with migration**, because a split
workspace (flat legacy + directory-form new) would make every cross-reference and
index permanently inconsistent, and the migration is mechanical (`git mv` preserves
history). Ze keeps `specs/core/` and `specs/arch/` untouched; spec-kit manages only
`specs/phases/`.

Concretely:

- `specify init --integration claude` scaffolding lives in `.specify/` and
  `.claude/skills/speckit-*`.
- `create-new-feature.sh` is patched: `SPECS_DIR` points at `specs/phases/` instead
  of `specs/`.
- Every `specs/phases/N-name.md` became `specs/phases/NNN-name/spec.md` (three-digit,
  zero-padded, `git mv`). `37-news-package-premortem.md` became
  `037-news-package/pre-mortem.md` — supporting documents live inside their feature
  directory, which is the spec-kit idiom.
- The constitution (`.specify/memory/constitution.md`) codifies the non-negotiables
  already in `CLAUDE.md`: spec-first, single-user model, layered packages, typed
  Python, test discipline, raw-SQL migrations, OpenRouter-only.
- All hand-copied templates (`TEMPLATE.md`, `TEMPLATE-phase.md`, `TEMPLATE-adr.md`,
  `TEMPLATE-core.md`) are retired; new feature specs come from
  `.specify/templates/spec-template.md` via `/speckit-specify`. Spec-kit has no ADR
  or infrastructure-spec concept — new `arch/` and `core/` documents follow the
  structure of the existing ones.

### Positive Consequences

- Research, contracts, data models, and task lists get first-class homes per feature
  instead of being crammed into one file or skipped.
- `/speckit-clarify` and `/speckit-analyze` add de-risking and consistency gates the
  old workflow lacked.
- Constitution check makes plans self-audit against Ze's architecture rules.
- Feature numbering, branch naming, and directory creation are scripted instead of
  manual.

### Negative Consequences / Trade-offs

- One-time churn: ~100 files moved, every path reference in docs/README/CLAUDE.md
  rewritten.
- `.specify/scripts/` is vendored shell that may drift from upstream spec-kit;
  upgrades require re-running `specify init` and re-applying the `SPECS_DIR` patch.
- Historical specs are `spec.md` files without plan/tasks siblings — the directory
  form implies a completeness they don't have (acceptable: they are Done).

---

## Pros and Cons of the Options

### Option 1 — Full adoption with migration

**Pros:**
- Uniform tree; one mental model; scripts and indexes work everywhere.
- History preserved via `git mv`.

**Cons:**
- Large one-time diff; all inbound links needed rewriting.

### Option 2 — New specs only

**Pros:**
- Zero migration churn.

**Cons:**
- Two coexisting conventions forever; `get_highest_from_specs` numbering only sees
  directory-form specs, risking number collisions with flat legacy files.

### Option 3 — Templates only

**Pros:**
- No new tooling to maintain.

**Cons:**
- Loses the actual value: the staged pipeline, clarify/analyze gates, constitution
  enforcement, and scripted feature creation.

---

## Links

- [GitHub spec-kit](https://github.com/github/spec-kit)
- [Ze Constitution](../../.specify/memory/constitution.md)
- [specs/README.md](../README.md) — updated workspace guide
