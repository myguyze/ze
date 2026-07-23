# Ze Doctrine — What Kind of Mind Ze Is

> **Status:** Accepted (constitutional)
> **Scope:** All packages. This is the top-level document every other spec is checked against.
> **Relationship to `VISION.md`:** the short product statement. This document is the
> constitutional expansion of those commitments — check every other spec against *this*.
> **Relationship to other docs:** `specs/arch/correlation-engine.md` is a *local* application
> of this doctrine (bounded, grounded, agency-preserving). This document generalises that
> discipline to the whole system.

---

## Why this document exists

Ze has, by any measure, unusually strong *local* discipline: per-package specs, ADRs, a
clean dependency graph, a real epistemic stance inside the correlation engine. What it did
not have, until now, was a **constitutional layer** — a stable answer to *what kind of mind
Ze is supposed to become*, independent of any one feature.

An external review put the risk precisely: the danger for a lifelong,
ever-growing system is **not** that it is too ambitious. It is that it becomes "a growing
collection of sophisticated mechanisms without a stable theory of what intelligence,
usefulness, continuity, and agency mean inside this system." Ambition does not license
conceptual looseness — it demands the opposite. Ze should not aim to be *simple*; it should
aim to be **legible at every stage of its complexity**.

This document is that theory. It is deliberately short on mechanism and long on commitments,
because mechanisms are replaceable and commitments are not. When a future spec conflicts
with this document, this document wins or this document is amended — never silently ignored.

---

## The one commitment: Ze is a world-state, not a chat loop

**The irreducible thing that must remain continuous across every refactor is Ze's
world-state: the living model of the user and their active concerns.**

Everything else is an organ attached to that spine and is, in principle, replaceable:

| Organ | Replaceable because |
|---|---|
| Personality / persona | It is literally dials and YAML today; it is presentation, not self. |
| Agents & tools | Interchangeable executors; the roster will churn for years. |
| Goals | One narrow, heavyweight unit of concern — not the universal unit of meaning. |
| The LLM(s) | Swapped via OpenRouter config; the model is rented cognition. |
| Memory *tables* | Storage of the world-state's history, not the world-state itself. |
| The orchestration graph | Mechanism for updating and acting on the world-state. |

None of these is the point. The point is that after any of them is torn out and rebuilt, Ze
must still know **who you are, what is true, what is open, and what is drifting.** That
continuity is the product. A companion that forgets its model of you every refactor is a
demo wearing a persona.

This resolves an important question: "what must remain continuous — memory, goals,
personality, model-of-you, or decision policy?" — it is the **model of you and your active
concerns**. Not personality (presentation), not goals (one unit), not the decision policy
(mechanism), and not raw memory (that is the *record*, the world-state is the *interpretation*).

### What "world-state" means, precisely

The world-state is **not** a world model. A world model is unbounded, ungroundable, and is
exactly where hallucinated correlations live (see `correlation-engine.md`). The world-state
is bounded to the user's neighbourhood: who and what *they* care about, are committed to, are
tracking, or are drifting on. It has four faces:

1. **Self-model** — who Ze is to this user: role, standing commitments, tone, boundaries.
2. **User-model** — who the user is: values, patterns, relationships, stable preferences.
3. **World-model (bounded)** — the entities/events/topics in the user's relevance set and
   their connections. Grows *only* along that relevance set. Never the world at large.
4. **Active concerns** — what is currently open, promised, planned, or in tension. This is
   the face that is most under-built today (see the Cognitive Architecture doc); goals are a
   heavyweight special case of it.

Memory is the *substrate* the world-state is reconstructed and revised from. The world-state
is the *interpretation* memory exists to serve.

---

## The epistemic ontology — what Ze is allowed to hold in mind

A companion that treats every stored string as equally true is a liability. Ze distinguishes
**kinds of claim**, and the kind determines how the claim is revised and how confidently it
is allowed to reach the user. This is the answer to "what is the difference between a fact, an
inference, a suspicion, a priority, and an identity claim?"

| Kind | What it is | Typical source | How it is revised | Surfacing posture |
|---|---|---|---|---|
| **Identity claim** | A stable truth about who the user *is* ("is a solo developer", "values directness") | Onboarding, repeated corroboration, explicit statement | Slowly; requires strong, repeated counter-evidence. Protected against churn. | Stated as known, rarely re-litigated. |
| **Fact** | A discrete, grounded statement ("meeting with X moved to Friday") | Conversation, calendar, email, ingestion | Superseded by newer facts; expires on `valid_until`; contradicted by NLI. | Stated plainly with provenance available. |
| **Inference** | A conclusion Ze derived, not observed ("this project is stalling") | Reflection, correlation, consolidation | Falls when its supporting facts fall; must cite the facts it rests on. | Hedged; "it looks like…", never asserted as fact. |
| **Suspicion** | A low-confidence hunch worth holding but not acting on ("these two events may be linked") | Correlation, dream synthesis | Cheap to hold, cheap to drop; promoted only on corroboration. | Offered as a question, with uncertainty explicit. Never a verdict. |
| **Priority** | A judgment about what deserves attention now ("the tax deadline outranks the newsletter") | Executive layer over active concerns | Recomputed continuously as state changes. | Drives *ordering* of what Ze surfaces, not its truth. |

Two properties are mandatory on **every** claim, regardless of kind:

- **Provenance** — where it came from, tagged honestly at the source, never from the model's
  narration. The correlation engine's rule generalises to the whole system: an inference
  built by live web search must **never** be presented as something Ze "recalled" or "knew".
  `graph_recall` ≠ `live_search` ≠ `prompt_supplied` ≠ `synthesized`.
- **Confidence + decay** — a claim carries how sure Ze is and how fast that certainty ages.
  Nothing is permanently true by default; identity claims decay slowest, suspicions fastest.

The load-bearing rule: **a claim may only be surfaced with a posture its kind and confidence
license.** Ze may hold a suspicion privately and act on an identity claim confidently, but it
may never present a suspicion as a fact or an inference as an observation. This single rule is
what keeps a cross-domain companion from degenerating into a confident conspiracy generator.

---

## The contribution model — how each function writes to the spine

The seven cognitive functions (`docs/cognitive-architecture.md`) are not merely a way to
audit completeness. They are the **enduring structure of the mind**, and they refine the
organ/spine distinction into two levels:

- **The functions are permanent.** A mind that perceives, remembers, decides, relates,
  reflects, acts, and governs will always have those seven capacities. They are not features;
  they are what "mind" decomposes into.
- **The implementations are the replaceable organs.** The news plugin is one implementation of
  perception; the goals module is one implementation of executive function. Organs churn;
  functions persist. So "what stays continuous" is sharper than the world-state *data* alone:
  it is the world-state **plus the functional decomposition around it.**

Each function contributes to the spine in a characteristic way, and — this is a governance
rule, not a convention — **may only produce the claim-kinds its function licenses:**

| Function | Writes to (spine face) | May produce | May **not** produce |
|---|---|---|---|
| Perception | world-model, active concerns | facts (with provenance) | inferences dressed as facts |
| Memory | custodian of all faces | retains & retrieves — asserts nothing new | novel claims (it stores, it does not conclude) |
| Executive | active concerns | priorities, open-loop state | facts about the world |
| Social cognition | user-model, world-model | identity/relationship claims, boundaries | — |
| Reflection | any face (as proposals) | inferences, suspicions | **facts** |
| Action | new perceptible facts (side effects) | records of what it did | claims about intent it was not given |
| Governance | metadata on every claim | confidence, consent, provenance, corrections | domain content |

The load-bearing rule: **reflection may never emit a fact.** The dream and correlation engines
*conclude*; they do not *observe*. Everything they produce is an inference or suspicion,
surfaced only with the posture its kind licenses, and it becomes a fact **only when perception
or the user corroborates it.** This is what stops synthesized cognition from silently promoting
hunches into the record — the most dangerous failure mode for a system that dreams. (The dream
pipeline already honours this in practice: its promotion gate — session diversity, temporal
spread, NLI groundedness, two adversarial critics — *is* the corroboration step that licenses a
synthesized inference to be written as a `provenance=synthesized` fact. The doctrine names the
principle that behaviour already follows.)

Every contribution is a **proposal** carrying its claim-kind, provenance, and confidence;
governance arbitrates (see below). The `SignalSource` hook (Phase 60) is the first instance of
this pattern — a signal is simply perception's proposal to the spine. The long-term
architectural direction is that **every** function contributes through the same uniform
proposal seam, rather than through ad-hoc writes to memory tables.

---

## Belief revision — how the model changes without losing itself

The world-state is not append-only memory; it is a **revised** interpretation. Revision is
governed, not incidental.

- **Newer grounded facts supersede older ones.** Contradiction is detected (NLI cross-encoder,
  Phase 79), not hoped for.
- **Inferences and suspicions are only as alive as their evidence.** When the facts they cite
  fall, they fall with them. No orphaned conclusions.
- **Everything decays.** `valid_until` and confidence aging mean stale beliefs die quietly
  rather than accumulating as sediment. Synthesized beliefs uncorroborated by raw experience
  expire (the dream pipeline's 90-day rule is the pattern, not the exception).
- **Reflection is the revisor, not a generator of free-floating novelty.** The dream /
  consolidation / insight loop earns its cost *only* by improving the world-state —
  sharpening the user-model, closing or re-prioritising active concerns, strengthening or
  retiring beliefs. Reflection that produces facts nothing consumes is indulgence and should
  be cut. (This is the precise, non-dismissive version of Codex's "dreaming may be ahead of
  evidence": it is ahead of evidence *iff* it has no world-state to serve.)

---

## Knowing you vs. overfitting to a stale you

"Knowing the user" and "overfitting to a snapshot of the user" look identical from inside the
model; the difference is only visible over time. Ze guards the boundary with three mechanisms:

- **Recency-weighted confidence.** A pattern from two years ago is not evidence about today
  unless it has been re-corroborated since.
- **The endorsement test.** Before an identity claim hardens, it should be the kind of thing
  the user would still endorse if asked. Claims the user has corrected are not merely dropped —
  the *correction* becomes a durable, high-confidence fact ("does not want X").
- **Stated beliefs outrank inferred ones.** What the user tells Ze about themselves outranks
  what Ze concluded about them. Ze is allowed to notice a divergence between the two (that is
  drift, and it is valuable), but it resolves such divergence *with* the user, not by
  overwriting them.

---

## Arbitration — Ze is one mind, not a router over specialists

When subsystems disagree — the calendar says one thing, an inference says another, two agents
propose conflicting actions — something must arbitrate. The commitment is: **Ze is the
arbiter, and the world-state is the single source of truth subsystems write proposals
against.** Agents and jobs do not hold private truths that compete peer-to-peer; they
*propose* changes to the shared world-state, and arbitration follows a fixed precedence:

```
governance (consent, capability, reversibility)
  > user-stated identity/preference
    > grounded fact (with provenance)
      > inference (must cite facts)
        > suspicion (must be offered, never enacted)
```

This is why Ze can *feel like one continuous companion rather than a router over modules*: 
the felt-unity does not come from the persona layer. It comes from every
subsystem reading from and writing to **one** world-state and **one** identity block, and from
a single arbitration order that resolves conflict the same way everywhere. Personality is the
voice; the shared world-state is the self.

---

## What this doctrine forbids (guards against premature closure)

A lifelong system dies when an early local convenience quietly hardens into metaphysics. These
are recorded as anti-patterns. Local uses are fine; becoming the ontology is not.

| Anti-pattern | Why it is forbidden as *ontology* |
|---|---|
| Everything is a chat turn | The world-state persists between and beyond turns; conversation is one input channel, not the substrate. |
| All knowledge is vector-searchable snippets | Identity, commitments, and structure are not bags of embeddings; the graph and world-state are first-class. |
| Goals are the universal unit of meaning | Goals are one heavyweight kind of active concern; most concerns are lighter and never become goals. |
| All domains contribute equally | Some domains are primary sources of truth; most are enrichment. Relevance, not symmetry, governs admission. |
| Autonomy is tool execution | Autonomy is *self-maintained world-state plus governed initiative*, not the ability to call an API without asking. |

---

## The open strategic question (deferred to next-phase iteration)

The **spine** is settled (world-state). The **aperture** — the product's centre of gravity —
is not, and is deliberately left open here. The live tension is between:

- **Open loops** — Ze as a command centre for unfinished business (promises, threads, pending
  decisions, drifting projects), where goals are just one kind of loop; and
- **Life-graph with an intervention engine** — build the bounded world-model explicitly and
  focus the product on *when intervention is warranted*.

These are frequently posed as rivals. They are better understood as **the same trajectory at
two time horizons**: "active concerns" (the fourth face of the world-state) is exactly the set
of open loops, and a mature open-loop tracker *is* a life-graph whose most valuable projection
is "what is unfinished." The intervention engine is not an alternative to either — it is the
**output discipline** both require, and the correlation engine already prototypes it (surface
a grounded hypothesis with uncertainty; leave agency intact).

The doctrine's only constraint on this decision: whatever aperture is chosen, it must be a
**projection of the world-state**, not a parallel structure beside it. The next-phase spec
will resolve which projection to build first. This document does not pre-empt it.

---

## Consequences

- **The correlation engine's doctrine is promoted to system-level.** Bounded, grounded,
  provenance-honest, agency-preserving — these are no longer properties of one engine; they
  are properties of Ze.
- **A world-state / active-concerns layer becomes a first-class gap to close.** It is the
  missing executive organ (see `docs/cognitive-architecture.md`). This is the most likely
  subject of the next phase.
- **Reflection (dream/consolidation/insights) is re-justified by a single test:** does it
  improve the world-state? Anything that does not is a candidate for removal, not expansion.
- **Every future spec inherits a checklist:** which claim kinds does it produce? Is provenance
  honest? Does it write to the shared world-state or invent a private truth? Does it preserve
  the arbitration order and human agency?

---

## Open Questions

- [ ] **Aperture** — open-loops-first vs. life-graph-with-intervention-first. Deferred to the
  next-phase iteration; both are valid projections of the agreed spine.
- [ ] **World-state materialisation** — is "active concerns" a new store/table, a derived view
  over existing memory + goals, or a hybrid? To be decided in the next-phase spec.
- [ ] **Confidence calibration** — the epistemic ontology assumes a usable confidence signal
  per claim; its source and calibration (LLM self-rating vs. corroboration count vs. feedback)
  is unresolved beyond the correlation engine's local scheme.
