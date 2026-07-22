# Contribution Seam — How the Seven Functions Write to the Spine

> **Status:** Proposed (design-only — no implementation until the executive layer needs it)
> **Scope:** `ze-plugin` (the seam itself), `ze-memory` / world-state (the target),
> `ze-core` governance (arbitration); every function-owning package downstream.
> **Constrained by:** `specs/arch/ze-doctrine.md` §The contribution model.
> **Relationship to the aperture:** the executive layer chosen in
> `specs/arch/aperture-decision.md` is the **first new function** that should be built on this
> seam rather than writing to tables directly.

---

## Context

The doctrine established that the seven cognitive functions each contribute to the world-state
in a licensed way, and named the direction: *"every function contributes through the same
uniform proposal seam, rather than through ad-hoc writes to memory tables."*

Today exactly **one** such seam exists — `SignalSource` (Phase 60), through which perception
proposes signals. Everything else writes directly: memory writes facts/episodes to its tables,
the dream pipeline writes synthesized artifacts, goals write to goal tables, correlation
returns hypotheses inline. There is no shared notion of "a function is proposing a change to
the spine, tagged with claim-kind + provenance + confidence, subject to arbitration."

This brief sets the grounds for generalising `SignalSource` into that shared seam. It is
explicitly **design-only**: the seam should not be built speculatively. It earns its existence
when the executive layer (aperture) gives it a second real client, so the abstraction is
extracted from two concrete cases — never invented ahead of one.

---

## The concept: a Contribution

A **Contribution** is a function's typed proposal to change the world-state. Every contribution
carries, at minimum, the metadata the doctrine already mandates on every claim:

| Field | Meaning | Doctrine tie-in |
|---|---|---|
| `claim_kind` | identity / fact / inference / suspicion / priority | §epistemic ontology — the function may only emit kinds it is licensed for |
| `provenance` | `graph_recall` / `live_search` / `prompt_supplied` / `synthesized` / … | honest at the source, never from narration |
| `confidence` | how sure + decay rate | governs surfacing posture |
| `target_face` | self / user / world / active-concerns | which face of the spine it writes |
| `source_function` | perception / memory / … | enforces the licensing table |
| `evidence` | IDs of claims it rests on | inferences/suspicions must cite; enables cascade retraction |

Governance **arbitrates** contributions in the doctrine's precedence order (governance >
user-stated > fact > inference > suspicion) before any of them mutate the world-state. A
contribution is a *request*, not a write.

The critical rule the seam mechanically enforces, that convention cannot: **a function may only
submit contributions of the claim-kinds it is licensed for** — most importantly, *reflection
may never submit a fact.* Making this a property of the type system, not a guideline, is half
the reason the seam is worth building.

---

## Mapping the seven functions

Reuses the doctrine's licensing table; here framed as "what each function's contributions look
like" and how far each is from the seam today.

| Function | Contributes | Today | Distance to seam |
|---|---|---|---|
| Perception | facts, candidate loops | `SignalSource` (partial — signals only) | **Closest** — generalise the existing hook |
| Memory | nothing new (custodian) | direct table writes | Memory is the *target*, not a contributor — mostly exempt |
| Executive | priorities, open-loop state | does not exist yet | **Built on the seam from day one** (aperture) |
| Social cognition | identity/relationship claims | contacts writes directly | Migrate after executive |
| Reflection | inferences, suspicions | dream/correlation write/return directly | High value — enforces "no facts from reflection" |
| Action | records of what it did | agents write results directly | Low priority — side effects, already grounded |
| Governance | confidence/consent/provenance metadata | capability gate, review flows | Governance *is* the arbiter, not a contributor |

Two functions are special: **memory is the target** (contributions land in it), and
**governance is the arbiter** (it evaluates contributions). The seam is really about the other
five *producing* into memory via governance.

---

## Design questions to resolve before speccing

- **Runtime type vs store.** Is a Contribution an in-process object arbitrated synchronously in
  the graph, a persisted queue (like the dream staging buffer), or both depending on function?
  (Perception/executive likely sync; reflection likely staged — it already is.)
- **Wrap or replace direct writes.** Does the seam *replace* `store.propose_facts()` etc., or
  wrap them? Incremental migration argues for wrapping first, hard-cut later.
- **Arbitration mechanism.** Is arbitration a real conflict-resolution step (two contributions
  disagree → precedence decides) or initially just a validated write path? Start with the
  latter; add genuine conflict resolution when two functions actually collide.
- **Relationship to existing seams.** `memory_policies()`, `signal_sources()`, and the dream
  staging buffer are all proto-contributions. The seam should *subsume* them, not sit beside
  them — otherwise it is a third pattern, not a unifying one.
- **Where the type lives.** `ze-plugin` (shared extension seam) is the natural home for the
  `Contribution` contract; the arbiter lives in `ze-core` governance; the target is the
  world-state store.

---

## Phased rollout sketch (not a commitment)

The seam must be **extracted from two real clients, not invented before one.** Suggested order:

1. **Executive layer ships (aperture, Option A).** It writes open-loop contributions — the
   *second* concrete client after `SignalSource`.
2. **Extract the `Contribution` contract** from the two clients (perception signals + executive
   loops). Generalise `SignalSource`; do not design in the abstract.
3. **Migrate reflection onto it.** Highest safety payoff: mechanically forbids dream/correlation
   from writing facts. The dream staging buffer becomes a contribution queue.
4. **Migrate social cognition** (relationship claims) and **action** (result records) as
   convenience allows. Low urgency.
5. **Add genuine arbitration** only once two functions demonstrably collide on the same
   world-state face.

Memory and governance are never "migrated" — they are the target and the arbiter.

---

## Consequences and risks

- **Positive:** enforces the doctrine's licensing rules in code, not prose; makes provenance and
  confidence universal rather than per-subsystem; unifies three existing proto-seams; gives the
  arbitration order a single chokepoint.
- **Risk — premature abstraction.** This is the doctrine's own anti-pattern ("a sentence that
  hardened into metaphysics"). Mitigated by the extract-from-two-clients rule: nothing here is
  built until the executive layer forces it.
- **Risk — performance.** A synchronous arbitration step sits in the hot path for
  perception/executive contributions. The correlation engine's inline latency discipline (hard
  timeout, silent drop) is the precedent to follow.
- **Risk — big-bang migration.** Avoided by wrapping before replacing and migrating one function
  at a time.

---

## Open Questions

- [ ] **Trigger to build.** Confirm the seam is extracted *after* the executive layer exists
  (this brief's assumption), not before.
- [ ] **Sync vs staged per function** — resolve which functions arbitrate inline vs via a queue.
- [ ] **Does `Contribution` replace `Signal`, or is `Signal` a `Contribution` subtype?**
- [ ] **Confidence source** — the doctrine's open question on calibrated confidence applies here;
  the seam needs a usable `confidence` value from every function.
