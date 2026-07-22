# Phase 0 Research: Open-Loop Substrate

All spec-level ambiguities were resolved during `/speckit-clarify` (see spec.md's
`## Clarifications` section: confidence representation, duplicate-matching signal, claim-kind
taxonomy origin, decay cascade timing, stale-suspicion expiry mechanism). This document
resolves the remaining **plan-level** technical unknowns — decisions the spec correctly left to
planning.

---

## 1. Package placement and wiring shape

**Decision**: `ze-worldstate` is a new **core** package, wired directly into `ze-api` — not a
`ZePlugin`.

**Rationale**: `specs/arch/ze-doctrine.md` names the open loop as the concrete form of the
world-state's fourth face ("active concerns"), part of the constitutional spine, not a domain
extension. `ze-automation` (goals/workflows) already establishes the precedent for this: a core
package that is not a `ZePlugin`, wired directly into `ze-api`'s `container.py`, `migrate.py`,
and `compose.py`, with its own `bootstrap.py` stack builder (`build_automation_stack`) and a
`rest.py` of plain-dict service functions consumed by `ze_api/api/routes/`. `ze-worldstate`
follows this shape exactly (`build_worldstate_stack`).

**Alternatives considered**:
- *A `ZePlugin` in `plugins/`* — rejected. Loops are not a domain the way calendar/finance/news
  are; they are infrastructure for *every* domain's inflows to write into, symmetric with how
  `ze-automation` (also cross-domain infra) is core, not a plugin.
- *Folding loops into `ze-memory`* — rejected. `ze-memory` is explicitly "custodian, asserts
  nothing new" per the doctrine's contribution table; a loop is executive-function state
  (priorities, open-loop lifecycle), a different function than memory's custody role. Keeping
  them separate packages (as goals/workflows are separate from memory) preserves that
  functional boundary while still letting `ze-worldstate` *depend on* `ze-memory` for entity
  resolution and the graph store.

---

## 2. Loop↔entity and loop↔evidence linking mechanism

**Decision**: Reuse the existing `memory_relationships` table and `GraphStore` protocol
(`ze-memory/ze_memory/graph/store.py`) rather than creating new join tables in
`ze-worldstate`. A loop↔entity link is a row with `source_type="entity"`,
`target_type="open_loop"` (so traversal from the entity reaches the loop, per SC-004); a
loop↔evidence link is a row with `source_type="open_loop"`, `target_type="fact"` or
`"episode"`.

`source_type`/`target_type` on `memory_relationships` are unconstrained `TEXT` columns (no enum,
no FK to a fixed type list — confirmed in `zm003_relationships.py`), so introducing
`"open_loop"` as a new type value requires no schema change to `ze-memory`. The one small
addition needed is a generic bucket for `"open_loop"` in `GraphStore.expand()`'s
`_TYPE_BUCKET` mapping (`ze_memory/graph/store.py`) and a matching field on
`GraphExpansion` (`ze_memory/graph/types.py`), so a loop surfaces when traversing an entity's
neighbourhood — the same one-line pattern used when the `"signal"` bucket was added. This is a
generic graph-substrate change (no domain knowledge added to `ze-memory`), consistent with the
constitution's layering.

**Rationale**: FR-012/FR-013 explicitly require loops to reuse memory's entity/relationship
substrate rather than duplicate it. A dedicated `loop_entity_links`/`loop_evidence_links` table
in `ze-worldstate` would be exactly the "parallel structure beside the world-state" the doctrine
forbids.

**Alternatives considered**:
- *New tables owned by `ze-worldstate`, referencing `memory_entities`/`memory_facts` by FK* —
  rejected: works mechanically but duplicates the relationship substrate `ze-memory` already
  provides, and traversal would need a second code path in addition to `GraphStore.expand()`.

---

## 3. Confidence decay cascade wiring (synchronous, cross-package)

**Decision**: The cascade (FR-004, fires synchronously at the evidence-writing code path) is
triggered by the *caller* that already touches both packages, not by `ze-memory` calling into
`ze-worldstate` directly (that would invert the dependency direction — `ze-memory` must not
depend on `ze-worldstate`). Concretely: wherever a fact/episode is marked contradicted, expired,
or retracted today (`ze_memory.consolidator`'s `mark_contradicted`, the write-time NLI
contradiction hook, episode expiry in consolidation), the call site — which already has both a
memory store and, once wired, a `LoopStore` — additionally calls
`ze_worldstate.decay.cascade_from_evidence(evidence_type, evidence_id)` immediately after the
memory-side write. In practice this means `ze-api`'s composition layer (or the specific
consolidation/write-path modules already invoked from `ze-api`) is the one place aware of both
stores, matching how other cross-package cascades in this codebase are wired (e.g.
accountability's anomaly detection reading from cost telemetry).

`cascade_from_evidence` looks up loops linked to the given evidence id via the
`loop_evidence_links`-equivalent `memory_relationships` rows (see §2) and applies the decay
function (see §4) to each.

**Rationale**: Preserves the layered dependency graph (`ze-worldstate → ze-memory`, never the
reverse) while still satisfying the "synchronous, not periodic" requirement from Clarification.

**Alternatives considered**:
- *`ze-memory` depends on `ze-worldstate` and calls it directly* — rejected: violates the
  dependency direction; `ze-memory` is lower-level infra than `ze-worldstate`.
- *Event bus / pub-sub between the packages* — rejected as premature infra: no such bus exists
  elsewhere in the codebase (the doctrine's own contribution-seam brief explicitly defers this
  kind of generalised mechanism until a second real client forces it); a direct call from the
  shared caller is simpler and matches existing patterns.

---

## 4. Decay function shape

**Decision**: Multiplicative decay — on contradiction/retraction, `confidence *= 0.0` (i.e., the
loop's confidence collapses to a low floor, since its evidentiary basis is gone) if it was the
loop's *sole* evidence; when a loop has multiple evidence links, confidence is recomputed as a
function of remaining (non-retracted) evidence weight, floor `0.05`, never exactly `0.0` (a
dropped-to-floor loop still exists for the user to see why it faded, consistent with dismissed
loops not disappearing silently — Edge Cases). Exact formula (weighted average vs. max vs.
decay-by-factor) is an implementation detail inside `ze_worldstate/decay.py`, not re-litigated
here; the **testable contract** is SC-006: confidence measurably drops when a cited fact is
contradicted or expires.

**Rationale**: Matches the confidence type resolved in Clarification (continuous float
0.0–1.0) and doctrine's "inferences are only as alive as their evidence."

---

## 5. Matching implementation (entity-overlap + embedding tiebreaker)

**Decision**: `ze_worldstate/matching.py` takes a candidate loop's resolved entity id(s) (from
`ze-memory`'s existing entity resolution, consumed not reimplemented per Assumptions) and:
1. Queries existing loops sharing at least one resolved entity (via `memory_relationships`).
2. If exactly one match, treat as the same loop (attach/strengthen per FR-010).
3. If zero or multiple candidate matches, or entity resolution is empty (e.g. no named entity in
   the utterance), fall back to embedding cosine similarity between the candidate's derived
   title and existing loops' titles, using the same injected embedder `ze-memory` already
   receives by constructor injection (no new embedding model dependency, per constitution).
   A threshold (plan-time tunable, not spec-mandated) decides same-loop vs. new-loop.

For dismissed-then-re-implied (FR-011), the same matching function is reused against loops in
`dropped` state whose dismissal originated from evidence overlapping the new candidate.

**Rationale**: Matches the Clarification answer exactly (entity overlap primary, embedding
tiebreaker secondary) and reuses existing injected infra rather than adding a new similarity
service.

---

## 6. Stale-suspicion expiry job

**Decision**: `ze_worldstate/jobs/stale_suspicion.py` is a `@proactive_job`-decorated class
(`ze_sdk.proactive` / `ze-proactive`'s `ProactiveJob` protocol), registered the same way
`CalendarReminderJob` is — via `register_proactive_jobs()`-equivalent wiring in `ze-api`'s
`compose.py`. It sweeps `suspected` loops older than the configured window (default 14 days,
per Assumptions) and transitions them to `dropped` (not deleted — consistent with "closing an
entity's last loop must not delete the shared entity," and with dismissed loops being
retrievable rather than vanishing).

**Rationale**: Directly resolved by Clarification #5.

---

## 7. Extraction relevance gate

**Decision**: Extraction (FR-008/009) reuses the salience/relevance concepts already introduced
by the correlation substrate (per Assumptions) rather than a new scoring model — i.e. the same
class of gating that keeps the correlation engine from surfacing noise is applied before a loop
candidate is even proposed. Extraction runs as an additional step alongside the existing
fact/episode-writing code path for each inflow (conversation turn processing, `ze-messenger`
inbound processing, `ze-calendar` sync, ingestion), calling
`ze_worldstate.extraction.propose_loop_candidates(...)` directly — the FR-017 proto-contribution
direct write, structured so the future contribution seam (`contribution-seam.md`) can absorb it
without a rewrite (the function signature carries `claim_kind`, `provenance`, `confidence`,
`evidence` — the same fields `Contribution` will need).

**Rationale**: Assumptions section is explicit that this reuses existing salience thinking and
existing extraction cadence; no new relevance model needed for Phase A.

---

## Summary of resolved unknowns

| # | Unknown | Resolution |
|---|---|---|
| 1 | Package placement/wiring | Core package, `ze-automation`-shaped, direct `ze-api` wiring |
| 2 | Loop↔entity/evidence storage | Reuse `memory_relationships` + `GraphStore`; one generic bucket added |
| 3 | Cross-package decay trigger | Shared caller invokes both stores; no new dependency direction |
| 4 | Decay function shape | Multiplicative/weighted-average, floor 0.05, exact formula is implementation detail |
| 5 | Matching algorithm | Entity-overlap primary, embedding-similarity tiebreaker, reuses injected embedder |
| 6 | Stale-suspicion job | `ze-proactive` job, same shape as `CalendarReminderJob` |
| 7 | Extraction relevance gate | Reuses correlation engine's existing salience concepts |

No `NEEDS CLARIFICATION` markers remain.
