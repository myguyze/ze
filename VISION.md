# Ze — Vision

Ze is a lifelong personal companion: a continuous model of you and your active concerns,
not a chat bot with plugins.

## The product

After any refactor, model swap, or agent churn, Ze must still know **who you are, what is
true, what is open, and what is drifting.** That continuity *is* the product.

The spine is the **world-state** — four faces, bounded to your neighbourhood:

1. **Self-model** — who Ze is to you (role, tone, boundaries)
2. **User-model** — who you are (values, patterns, relationships)
3. **Bounded world-model** — the people, projects, and events you care about
4. **Active concerns** — what is open, promised, planned, or drifting

Everything else (persona, agents, goals, LLMs, memory tables, orchestration) is a
replaceable organ attached to that spine.

## How it thinks

Ze is one mind writing to one world-state — not a router over specialists. Claims have
kinds (identity, fact, inference, suspicion, priority), honest provenance, and decaying
confidence. A claim may only be surfaced with the posture its kind licenses.

Seven enduring functions structure the mind: perception, memory, executive, social
cognition, reflection, action, governance. Implementations churn; the functions do not.
Today the primary gap is **executive function** — lightweight open loops, not just
heavyweight goals.

## Non-goals

- Not a general world model (unbounded = ungroundable)
- Not "autonomy = calling APIs without asking" (autonomy = self-maintained world-state
  plus governed initiative)
- Not goals-as-the-unit-of-meaning (goals are one kind of active concern)
- Not a chat loop as substrate (conversation is one input channel)

## Where the detail lives

| Doc | Role |
|---|---|
| [`specs/arch/ze-doctrine.md`](specs/arch/ze-doctrine.md) | Constitutional commitments — claim kinds, arbitration, contribution model |
| [`docs/cognitive-architecture.md`](docs/cognitive-architecture.md) | Functional map of the mind — maturity, gaps, sequencing |
