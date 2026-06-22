# Convergence & Pressure Points — Design Spec (Horizon)

> **Package:** `ze-correlation`
> **Phase:** 61
> **Status:** Pending (design-only — phases 55–60 shipped; implement after Phase 71)
> **Depends on:** Correlation Engine ([57-correlation-engine.md](57-correlation-engine.md)), Cross-Plugin Signal Contract ([60-signal-source-contract.md](60-signal-source-contract.md)), Correlation Engine ADR ([../arch/correlation-engine.md](../arch/correlation-engine.md))

---

## Purpose

This is the "Jarvis / psychohistory" horizon, captured so it is not lost — but explicitly
deferred. Phases 55–58 give Ze pairwise correlation: "event A relates to event B". This
phase asks the harder question: when do *several* signals and trends **converge** into a
larger pattern, and where are the **pressure points** — the small places where a user's
attention or action has outsized leverage?

It is recorded as design-only because it is only tractable once the relevance-bounded
graph (55–58) exists and the surfacing bar is calibrated. Attempting it earlier is the
"world model" trap the ADR warns against.

---

## The Asimov framing (made operational)

Psychohistory's usable kernel for a single-user assistant:

- Do **not** predict deterministically. Surface probable trajectories and their
  uncertainty.
- Identify **pressure points**: where a small, timely intervention has disproportionate
  effect on something the user cares about.
- **Preserve agency**: output is decision support — options, trade-offs, confidence —
  never an instruction. ("Violence is the last refuge of the incompetent"; coercion of any
  kind, including nudging-by-omission, is out of bounds.)

The unit of value is not a prediction; it is a **well-framed choice** delivered at the
moment it still matters.

---

## What "convergence" means here

Beyond pairwise correlation:

- **Theme clustering** — group recent hypotheses/events by shared entities and topics into
  a small number of live themes (e.g. "AI governance pressure on Anthropic").
- **Trajectory** — for a theme, summarize direction and momentum from its event sequence,
  with explicit uncertainty bands, not point predictions.
- **Convergence detection** — flag when independent themes start sharing entities or
  reinforcing each other (multiple sources, multiple domains, same direction).
- **Pressure point identification** — within a theme/trajectory, surface where the user
  has leverage or exposure (a decision window, a relationship, a goal at risk), tied to the
  user's actual goals and relevance set.

---

## Out of Scope (for this spec, and possibly forever)

- Acting autonomously on a pressure point. This layer proposes; the user (or an existing
  goal/workflow with explicit confirmation) acts.
- Modeling third parties' behavior beyond what grounded signals support.
- Any population-level or multi-user modeling. This remains a single-user assistant.
- Persuasion or sentiment shaping. Output is neutral decision support.

---

## Sketch (not a contract)

```python
@dataclass
class Theme:
    id: UUID
    label: str
    entities: list[UUID]
    hypotheses: list[UUID]       # contributing Phase 57 hypotheses
    trajectory: str              # hedged narrative of direction + momentum
    confidence: float

@dataclass
class PressurePoint:
    theme_id: UUID
    description: str             # where leverage/exposure exists
    linked_goal_id: UUID | None  # tie to an existing goal when relevant
    options: list[str]           # choices framed for the user, with trade-offs
    horizon: str                 # when it stops mattering
    confidence: float
```

Delivery would reuse the weekly narrative / accountability surface rather than ad-hoc
pushes — convergence is a reflective, periodic output, not an interrupt.

---

## Preconditions before implementing

- [ ] 55–60 shipped; inline correlation (Phase 58) demonstrably useful (positive feedback rate).
- [ ] Surfacing bar calibrated; false-positive rate acceptably low.
- [ ] Graph has enough cross-domain density (≥2 signal sources live) for convergence to
  mean anything.
- [ ] Cost envelope understood — theme/trajectory synthesis is heavier than pairwise.

---

## Open Questions

- [ ] Is convergence detection a clustering problem over the hypothesis store, or a
  recurring LLM synthesis over themes? (Probably both: cheap clustering to form themes,
  LLM to narrate trajectory.)
- [ ] How to express uncertainty bands honestly without false precision? Scenarios with
  likelihoods, or qualitative hedging only?
- [ ] Pressure points risk becoming prescriptive. What guardrails keep output as framed
  choices rather than nudges?
- [ ] Does this belong in `ze-correlation`, or is it a distinct "foresight" layer that
  consumes correlation output?
- [ ] How do we evaluate this at all? A trajectory is "right" or "wrong" only in
  hindsight — what's the offline eval story?
- [ ] Where is the hard line between "decision support that preserves agency" and "an
  assistant quietly steering its user"? This needs an explicit, written principle before
  any code.
