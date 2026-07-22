# Feature Specification: Open-Loop Substrate

**Feature Branch**: `109-open-loop-substrate`

**Created**: 2026-07-21

**Status**: Draft

**Input**: User description: "Open-Loop Substrate — the world-state executive layer (Phase A of two). A new `ze-worldstate` package making the doctrine's 'active concerns' face a first-class primitive: the open loop."

**Governed by**: [`specs/arch/ze-doctrine.md`](../../arch/ze-doctrine.md) (constitutional) and [`specs/arch/aperture-decision.md`](../../arch/aperture-decision.md) (Option A ratified). This is **Phase A of two**; Phase B (drift detection + surfacing) is outlined at the end and deliberately **not** specified here.

---

## Overview

Ze can perceive, remember, reflect, and act, but it has no first-class representation of *what
is currently open, promised, or unfinished in the user's life*. Goals cover only the
heavyweight end — objectives the user explicitly declares. The hundreds of small **open
loops** that make up a real life (a promise in an email, a decision left pending, a "I should
look into X" said once, a project whose dependency stalled) are never held anywhere.

This feature introduces the **open loop** as a first-class primitive in a new `ze-worldstate`
package — the concrete form of the doctrine's fourth face of the world-state, "active
concerns." Phase A is the **substrate only**: capture a loop honestly, hold it with the right
epistemic posture, let the user confirm or close it, and link it into the existing world
(memory graph) so it is a *projection of the world-state*, not a parallel to-do list. It does
**not** yet detect drift or decide when to surface a loop unprompted — that is Phase B.

The doctrine's discipline applies throughout: a loop Ze *inferred* is an inference/suspicion,
not an observed fact, and must not be acted on until corroborated.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A promise is captured and held as a suspicion until confirmed (Priority: P1)

Ze notices, from something the user said or an email thread, that there is likely an open loop
("you told Maria you'd send the contract this week"). It captures the loop as a low-confidence
**suspicion** with honest provenance and surfaces it for the user to confirm — it does not
silently treat it as a real commitment or act on it.

**Why this priority**: This is the core of the substrate and of the ratified epistemic posture.
Without it there is no honest capture, and the "active concerns" face stays empty. It is the
MVP: capture + posture + review is already useful and independently demonstrable.

**Independent Test**: Feed a conversation turn or email that implies a commitment; verify a loop
is created in `suspected` state with correct provenance and evidence links, that it appears in
the user's review surface, and that Ze does not act on it while unconfirmed.

**Acceptance Scenarios**:

1. **Given** a conversation turn where the user says "I really need to renew my passport before
   the trip", **When** the turn is processed, **Then** a loop titled around "renew passport" is
   created in `suspected` state, tagged with provenance `conversation`, low confidence, and
   linked to the evidence (the episode/fact it was derived from).
2. **Given** a `suspected` loop, **When** the user is shown their pending loops, **Then** the
   loop appears in a review list with its evidence, and Ze has taken no autonomous action on it.
3. **Given** a `suspected` loop, **When** the user confirms it, **Then** the loop transitions to
   an active, acted-on state with raised confidence; **When** the user dismisses it, **Then** it
   is dropped and does not reappear from the same evidence.

---

### User Story 2 - The user declares a loop directly and it is trusted immediately (Priority: P1)

The user explicitly tells Ze about unfinished business ("remind me I need to follow up with the
accountant", "I'm meaning to fix the fence"). Because it is user-stated, the loop is a
commitment from the start — it is not held as a suspicion and needs no confirmation.

**Why this priority**: The doctrine ranks user-stated claims above inferred ones. Declared loops
are the highest-confidence, lowest-risk inflow and must be distinguishable from inferred ones by
posture and provenance. Pairs with Story 1 to cover both admission paths.

**Independent Test**: Have the user explicitly state a task; verify a loop is created in an
active state (not `suspected`), with provenance `user_declared` and full confidence, with no
confirmation step required.

**Acceptance Scenarios**:

1. **Given** the user says "I need to follow up with the accountant next week", **When** the turn
   is processed, **Then** a loop is created directly in `active` state with provenance
   `user_declared` and no pending confirmation.
2. **Given** a user-declared loop, **When** the user later says it is done, **Then** the loop
   transitions to `closed`.

---

### User Story 3 - Loops connect to the rest of the world, not a silo (Priority: P2)

A loop about "the tax filing" is automatically associated with the same underlying entity as a
related calendar event and a related contact, so that a loop, an event, and a person about the
same thing form one neighbourhood rather than three disconnected records.

**Why this priority**: The doctrine requires loops to be a *projection of the world-state*, not a
flat parallel table. This is what separates the open-loop layer from a generic task list and is
the seam Phase B and correlation will build on. Lower than P1 because capture/posture is usable
before graph linkage is complete, but it is what makes the layer doctrinally correct.

**Independent Test**: Create a loop mentioning a known entity (a contact or topic already in the
memory graph); verify the loop resolves to and links the existing entity rather than creating a
duplicate, and that traversing from the entity reaches the loop.

**Acceptance Scenarios**:

1. **Given** a contact "Maria" already exists as an entity, **When** a loop "send Maria the
   contract" is created, **Then** the loop is linked to the existing Maria entity, not a new one.
2. **Given** a loop linked to an entity, **When** the neighbourhood of that entity is retrieved,
   **Then** the loop is reachable as part of that neighbourhood.

---

### User Story 4 - The user reviews and manages their open loops (Priority: P2)

The user can see their open loops, distinguish confirmed commitments from suspected ones, and
move each through its lifecycle: confirm, close (done), or drop (not real / no longer relevant).

**Why this priority**: Makes the substrate observable and controllable — the "memory as editorial
problem" principle applied to loops. Required for the feature to deliver visible value, but sits
on top of the P1 capture mechanics.

**Independent Test**: With a mix of `suspected` and `active` loops present, exercise the read and
lifecycle-transition surface and verify each transition persists and is reflected on next read.

**Acceptance Scenarios**:

1. **Given** several loops in different states, **When** the user lists their loops, **Then** each
   loop's title, state, provenance, and confidence are visible and suspected loops are clearly
   distinguished from confirmed ones.
2. **Given** any loop, **When** the user closes or drops it, **Then** its state updates
   accordingly and it no longer appears among active concerns.

---

### Edge Cases

- **Duplicate capture**: the same underlying loop is implied by two different inflows (a
  conversation and an email). The system must recognise the existing loop and strengthen/attach
  evidence rather than create a second loop.
- **Dismissed-then-re-implied**: a user dismissed a suspected loop, but the same evidence pattern
  recurs. It must not resurface from evidence the user already rejected.
- **Stale suspicion**: a `suspected` loop is never confirmed or dismissed. It must not accumulate
  forever — see Assumptions for the default decay behaviour.
- **Evidence retraction**: a fact/episode a loop was derived from is later contradicted or
  expired. The loop's confidence must be affected (cascade), consistent with the doctrine's
  "inferences are only as alive as their evidence."
- **Closing an entity's last loop**: closing a loop must not delete the shared entity it linked
  to; entities are owned by memory, not by loops.
- **Noise pressure**: an ordinary conversational turn with no real commitment must *not* mint a
  loop; extraction is relevance-gated and conservative.

---

## Requirements *(mandatory)*

### Functional Requirements

**Primitive & lifecycle**

- **FR-001**: The system MUST represent an *open loop* as a first-class record with, at minimum, a
  human-readable title/description, a lifecycle state, a claim kind, provenance, a confidence
  value, and links to the evidence it was derived from.
- **FR-002**: The system MUST support the lifecycle states `suspected → active → drifting →
  closed | dropped`, and MUST implement, in Phase A, all transitions **except** the automatic
  `active → drifting` transition (that automatic detection is Phase B). The `drifting` state
  MUST exist in the model so Phase B adds detection without a schema change.
- **FR-003**: Every loop MUST carry honest provenance identifying where it came from
  (`conversation`, `email`, `calendar`, `ingestion`, `user_declared`, …), assigned from the
  actual source and never from model narration.
- **FR-004**: Every loop MUST carry a confidence value, represented as a continuous float in the
  range 0.0–1.0, and MUST decay/weaken when the evidence it rests on is contradicted, expired, or
  retracted (cascade), per the doctrine. This cascade MUST fire synchronously at the point the
  evidence-writing code path detects the contradiction, expiry, or retraction — not via a
  periodic sweep — consistent with `ze-memory`'s existing write-time contradiction check.

**Epistemic posture (ratified)**

- **FR-005**: A loop that Ze *inferred* from perception MUST be created in the `suspected` state
  at low confidence and MUST NOT be acted on autonomously until the user corroborates it.
- **FR-006**: A loop the user *declared explicitly* MUST be created in an `active` (acted-on)
  state at high confidence with provenance `user_declared`, and MUST NOT require a confirmation
  step.
- **FR-007**: The system MUST provide a confirmation path for `suspected` loops that mirrors the
  existing propose→review pattern used for memory facts and contacts (propose, user reviews,
  confirm or dismiss). Confirmed loops become `active`; dismissed loops become `dropped`.

**Extraction (perception proposes loops)**

- **FR-008**: The system MUST be able to derive candidate loops from at least these inflows:
  conversation turns, email/messenger threads, calendar, and ingestion.
- **FR-009**: Loop extraction MUST be conservative and relevance-gated so that ordinary content
  does not generate loops; it MUST NOT create a loop for every statement.
- **FR-010**: When new evidence implies a loop that already exists, the system MUST attach the
  evidence to and/or strengthen the existing loop rather than create a duplicate. "Already
  exists" is determined primarily by overlap with the loop's linked resolved memory-graph
  entity/entities, using title/description embedding similarity as a secondary tiebreaker when
  entity overlap alone is ambiguous.
- **FR-011**: The system MUST NOT resurface a loop from evidence the user has already dismissed,
  using the same entity-overlap-plus-embedding-similarity matching as FR-010 to recognise
  recurrence of previously dismissed evidence.

**World-state projection (not a silo)**

- **FR-012**: A loop MUST link to resolved entities in the existing memory graph rather than
  storing its own copies of people/topics; a loop, an event, and a contact about the same thing
  MUST resolve to one shared entity and be reachable as one neighbourhood.
- **FR-013**: Closing or dropping a loop MUST NOT delete shared entities or evidence owned by
  memory.

**Surface & management**

- **FR-014**: Users MUST be able to list and retrieve their open loops, with each loop's state,
  provenance, and confidence visible, and with `suspected` loops clearly distinguished from
  confirmed ones.
- **FR-015**: Users MUST be able to transition a loop through its lifecycle: confirm a suspected
  loop, close a loop (done), or drop a loop (not real / no longer relevant).

**Boundaries with existing systems**

- **FR-016**: This feature MUST NOT modify the goal engine or goal schema. A loop MAY optionally
  reference a goal, but loops and goals remain parallel primitives; no unification occurs here.
- **FR-017**: Loop extraction is a *proto-contribution*: it MUST be implemented as a direct write
  through the loop layer for now, structured so the future uniform contribution seam
  ([`contribution-seam.md`](../../arch/contribution-seam.md)) can absorb it later without a
  rewrite. The seam itself MUST NOT be built in this phase.

### Key Entities *(include if feature involves data)*

- **Open Loop**: a single unit of unfinished business. Attributes: title/description, lifecycle
  state (`suspected`/`active`/`drifting`/`closed`/`dropped`), claim kind (identity/fact/
  inference/suspicion/priority — loops are typically suspicion when inferred, commitment when
  declared; this is the first code implementation of the doctrine's claim-kind taxonomy, defined
  in `ze-worldstate` with values matching `ze-doctrine.md` exactly), provenance, confidence
  (continuous float 0.0–1.0) + decay, timestamps, optional reference to a goal.
  Relationships: links to one or more memory-graph entities; links to the evidence
  (facts/episodes/signals) it was derived from.
- **Loop Evidence link**: the association between a loop and the memory items that justify it,
  enabling cascade retraction and the review surface's "why does Ze think this?" transparency.
- **Loop ↔ Entity link**: the association between a loop and existing memory-graph entities,
  making the loop part of the world-state neighbourhood (reuses memory's entity/relationship
  substrate; does not duplicate it).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ze can capture an open loop from a real inflow (e.g. a promise in an email or a
  statement in conversation), and the loop is held with correct provenance and low confidence —
  **without any goal being created**. The "active concerns" face of the world-state is no longer
  empty.
- **SC-002**: 100% of inferred loops are held in the `suspected` state and are never acted on
  autonomously before the user confirms them; 100% of user-declared loops are trusted immediately
  without a confirmation step.
- **SC-003**: The user can move any loop through its full lifecycle (confirm, close, drop) and the
  change persists and is reflected on the next read.
- **SC-004**: A loop about a subject already known to Ze links to the existing entity in ≥95% of
  cases rather than creating a duplicate, and the loop is reachable when traversing that entity's
  neighbourhood.
- **SC-005**: On a representative sample of ordinary conversation that contains no real commitment,
  the system creates no loops (no false-positive loop minted from noise), demonstrating the
  relevance gate.
- **SC-006**: When a fact a loop was derived from is contradicted or expired, the loop's confidence
  measurably drops (cascade), demonstrating evidence-linked belief.

---

## Clarifications

### Session 2026-07-21

- Q: How should a loop's confidence value be represented? → A: Continuous float 0.0–1.0, decays multiplicatively/additively on evidence retraction.
- Q: What signal determines that new evidence implies an *existing* loop rather than a new one (duplicate capture / dismissed-then-re-implied)? → A: Entity-link overlap (shared resolved entity) plus embedding similarity on title as a tiebreaker.
- Q: Where does the loop's "claim kind" enum (identity/fact/inference/suspicion/priority) come from — is it an existing type reused from elsewhere, or new? → A: No existing implementation of this taxonomy exists in code (it is only described in `specs/arch/ze-doctrine.md` and `contribution-seam.md`); this feature defines the enum for the first time in `ze-worldstate`, with values fixed to match the doctrine exactly so the future contribution seam can adopt the same type.
- Q: When does the confidence decay cascade (FR-004) actually fire — synchronously when evidence is contradicted/expired/retracted, or via a periodic sweep? → A: Synchronous/event-driven — the cascade fires immediately at the evidence-writing code path that detects contradiction, expiry, or retraction, consistent with `ze-memory`'s existing write-time contradiction check.
- Q: How is the ~14-day stale-suspicion expiry (Assumptions) mechanically enacted? → A: A new `ze-proactive` job in `ze-worldstate`, reusing the existing `ProactiveScheduler`/job pattern (same shape as `CalendarReminderJob`/goal jobs), sweeping and expiring stale `suspected` loops.

## Assumptions

- **Stale suspicion decay**: `suspected` loops that are neither confirmed nor dismissed expire
  automatically after a bounded window (default assumption: ~14 days) so they do not accumulate.
  Exact window is a plan-time detail; the behaviour (they must not live forever) is required.
  Expiry is enacted by a scheduled `ze-proactive` job (reusing the existing
  `ProactiveScheduler`/job pattern, e.g. `CalendarReminderJob`'s shape) rather than lazy
  on-read checks or a new scheduling mechanism.
- **Relevance gating reuses existing salience thinking**: extraction leans on the same
  relevance/salience concepts introduced by the correlation substrate rather than inventing a new
  scoring model.
- **Confirmation surface reuses existing patterns**: the review/confirm flow follows the existing
  memory-facts / contacts propose→review pattern and its transport; no new heavyweight UI paradigm
  is introduced in Phase A (a functional review surface is sufficient).
- **Single-user model**: consistent with the constitution — no per-user scoping; loops belong to
  the one user.
- **Entity resolution exists**: relies on the memory graph's existing entity resolution to link
  loops to people/topics; this feature consumes it and does not reimplement it.
- **Extraction cadence**: loop extraction runs as part of, or immediately after, the same
  processing that already writes facts/episodes for an inflow; it does not require a new
  user-facing step.

---

## Out of Scope (Phase B — outlined, not specified here)

The following are explicitly deferred to Phase B and MUST NOT be built in this phase:

- **Automatic drift detection** — the heuristics that move an `active` loop to `drifting` when
  reality diverges from its implied plan.
- **Proactive / inline surfacing and the interruption bar** — deciding *when* a loop earns a
  mention or a push, reusing the correlation engine's inline-vs-push asymmetry and calibrated
  bar. Phase A only surfaces loops on explicit user request (review/list).
- **Goal ↔ loop unification** — any change making a goal a kind of loop, or any goal-schema
  refactor.
- **The uniform contribution seam / arbitration engine** — generalising `SignalSource` and loop
  extraction into one proposal seam; design-only per [`contribution-seam.md`](../../arch/contribution-seam.md).
