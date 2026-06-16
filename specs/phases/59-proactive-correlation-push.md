# Proactive Correlation Push — Spec

> **Package:** `ze-correlation`, `ze-proactive`
> **Phase:** 59
> **Status:** Deferred (post-v1 — implement only after Phase 58 inline is trusted)
> **Depends on:** Correlation Engine ([57-correlation-engine.md](57-correlation-engine.md)), Salience Model ([56-salience-relevance-model.md](56-salience-relevance-model.md)), Inline Correlation ([58-inline-correlation.md](58-inline-correlation.md)), Proactive Ze ([15-proactive-ze.md](15-proactive-ze.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| `CorrelationJob` proactive consumer | 🔲 Deferred |
| Push bar + novelty/budget gating | 🔲 Deferred |
| Feedback on pushes | 🔲 Deferred |
| Scheduling + dry-run calibration | 🔲 Deferred |
| Tests | 🔲 Deferred |

---

## Purpose

The correlation engine (Phase 57) forms hypotheses; the inline surface (Phase 58) shows
them when the user asks. This phase adds the **second consumer**: a scheduled job that runs
over recently admitted signals and **pushes** qualifying hypotheses via
`ProactiveNotifier` — unprompted, interrupting the user.

**This is explicitly out of v1 scope.** v1 ships inline-only (Phase 58). The proactive
push is layered on only after inline feedback validates that the engine recalls and
connects reliably. The interrupt bar, novelty gate, and budget calibration are the hard
problems; deferring them avoids building spam machinery before the core works.

---

## Responsibilities

- Implement `CorrelationJob` (`@proactive_job`, `job_id = "correlation_scan"`).
- Select recently admitted signal-events as seeds (watermark-based), capped per run.
- Call `CorrelationEngine.correlate(seeds, mode="proactive")`.
- Apply the Phase 56 **push bar** (high): recall guarantee + `τ_push` + relevance +
  novelty + budget.
- Push qualifying hypotheses via `ProactiveNotifier` with feedback actions (useful / not
  relevant / mute topic).
- Route feedback to the Phase 56 threshold tuner.
- Support `dry_run` mode that logs would-be pushes without sending (calibration).

---

## Out of Scope

- The engine core (Phase 57) and inline surface (Phase 58).
- Signal admission (Phase 56) and anchoring (Phase 55).
- Cross-plugin `SignalSource` (Phase 60).
- Convergence (Phase 61).

---

## Module Location

```
core/ze-correlation/ze_correlation/
    job.py              # CorrelationJob (@proactive_job) — added in this phase
    push.py             # run_once(): seed selection, push bar, delivery
```

Container wiring follows existing proactive patterns: `@proactive_job` +
`register_proactive_jobs`, or `add_cron_job` like consolidation.

---

## Interface Contract

```python
# core/ze-correlation/ze_correlation/push.py

class CorrelationPushConsumer:
    def __init__(
        self,
        engine: CorrelationEngine,
        relevance_model,
        notifier,                # ze_proactive ProactiveNotifier
        push_log,                # ze_proactive PushLogStore
        settings,
    ) -> None: ...

    async def run_once(self, *, seeds: list[UUID] | None = None) -> list[Hypothesis]:
        """Pick recent signal seeds (or use given ids), correlate(mode="proactive"),
        apply the Phase 56 push bar, push qualifiers via ProactiveNotifier.
        Returns all hypotheses formed; a subset are pushed."""
```

```python
# core/ze-correlation/ze_correlation/job.py

@proactive_job
class CorrelationJob:
    job_id = "correlation_scan"
    async def run(self) -> None: ...     # calls push_consumer.run_once()
```

---

## Push bar (from Phase 56)

A hypothesis is pushed only if **all** hold:

| Condition | Threshold |
| --------- | --------- |
| Recall guarantee | ≥2 distinct `graph_recall` items |
| Correlation confidence | `>= τ_push` |
| Relevance to user | `>= τ_rel` |
| Novelty | not embedding-similar to a recent push |
| Push budget | within rate limit |

Sub-bar hypotheses persist with `surfaced=false` for digest/on-demand recall.

---

## Configuration

```yaml
# config/config.yaml
correlation:
  push:
    enabled: false              # off by default until Phase 58 validates inline
    schedule: "0 */4 * * *"
    max_seeds_per_run: 20
    dry_run: true               # log would-be pushes during calibration
    max_pushes_per_day: 3
```

---

## Preconditions before implementing

- [ ] Phase 58 inline shipped and receiving positive feedback.
- [ ] False-positive rate on inline connections acceptably low.
- [ ] Push bar thresholds calibrated from inline feedback data.
- [ ] `dry_run` exercised in production for at least one week with acceptable signal.

---

## Test Plan

- Seed selection respects watermark and `max_seeds_per_run`.
- Push bar integration: confidence/relevance/novelty/budget all enforced.
- Pushed hypotheses persist with `surfaced=true`; sub-bar ones with `surfaced=false`.
- Feedback action updates `feedback` and calls the Phase 56 tuner.
- `dry_run` logs would-be pushes and sends nothing.
- `enabled: false` by default — job registers but does not push until explicitly enabled.

---

## Open Questions

- [ ] Event-triggered vs purely scheduled — does a high-magnitude admit warrant
  `trigger_now`, or is a fixed cadence enough?
- [ ] Dedup with inline: if the same connection was just shown inline, suppress the push?
- [ ] When to flip `enabled: false` → `true` — manual config, or automatic after N
  positive inline feedback events?
