# Cross-Plugin Signal Contract — Spec

> **Package:** `ze-agents` (`ZePlugin`), `ze-sdk`, all signal-emitting plugins
> **Phase:** 60
> **Status:** Done
> **Depends on:** Signal Substrate ([55-signal-substrate.md](../055-signal-substrate/spec.md)), Correlation Engine ([57-correlation-engine.md](../057-correlation-engine/spec.md)), Plugin Framework ([47-plugin-framework.md](../047-plugin-framework/spec.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| `SignalSource` protocol + `ZePlugin` hook | ✅ Done |
| SDK re-export | ✅ Done |
| News migrated to the hook | ✅ Done |
| Second emitter (calendar) | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Phase 55 wired the news emitter directly to prove the substrate. This phase generalizes it
into a first-class plugin contract so any plugin — finance, legal, calendar, email — can
contribute factors to correlation with **zero changes to the engine**. This is the payoff
of the plugins-first architecture: "any plugin contributes a factor" becomes a one-method
contract.

---

## Responsibilities

- Define a `SignalSource` protocol: how a plugin produces `Signal`s for admission.
- Add a `signal_sources()` hook to `ZePlugin`, collected like `memory_policies()` and
  `agent_module_paths()`.
- Wire collected sources into the admission gate (Phase 56) and substrate (Phase 55) at
  container startup.
- Migrate news from its direct Phase-55 wiring onto the hook.
- Prove generality with a second emitter from a different domain.

---

## Out of Scope

- The salience math (Phase 56) and the correlation loop (Phase 57).
- Building new domain plugins (finance/legal). This phase adds an emitter to an existing
  plugin, it does not create a domain.
- A streaming/event-bus abstraction. Sources are pulled on the correlation/fetch cadence;
  a push bus is a possible later optimization, not part of v1.

---

## Interface Contract

```python
# core/ze-agents/ze_agents/signals.py  (new)

@runtime_checkable
class SignalSource(Protocol):
    source_key: str
    async def poll(self, since: datetime) -> list[Signal]:
        """Return salient candidate signals produced since `since`.
        The admission gate (Phase 56) decides which are ingested."""
```

```python
# core/ze-agents/ze_agents/plugin.py  (ZePlugin — addition)

class ZePlugin(ABC):
    def signal_sources(self) -> list[SignalSource]:
        """Sources this plugin contributes to correlation. Default: none."""
        return []
```

Re-exported via `ze_sdk` so plugin authors import `SignalSource` and `Signal` from the SDK
surface, consistent with the rest of the plugin API.

### Collection & wiring

Mirrors existing plugin-collection patterns in `apps/ze-api/ze_api/container.py`:

```python
signal_sources = collect_plugin_signal_sources(plugins)   # dedupe by source_key
correlation_engine.register_sources(signal_sources)
```

Duplicate `source_key` raises `AgentConfigError`, matching the duplicate-agent-key rule
for memory policies.

---

## Pull vs Push

v1 is **pull**: the admission cycle calls `source.poll(since)` on each registered source on
a cadence (aligned with each domain's fetch job). Pull keeps ordering, watermarks, and
backpressure simple and reuses existing fetch schedules.

A plugin that already fetches on its own schedule (news `NewsFetchJob`) can instead push
newly-fetched items straight into admission; `poll()` then returns the buffered delta. The
contract supports both; the engine does not care which.

---

## Migration

1. Add `SignalSource`/`signal_sources()` to `ze-agents`; re-export via `ze-sdk`.
2. Implement `NewsSignalSource(source_key="news")` wrapping `ArticleSignalAdapter`
   (Phase 55); register it via `NewsPlugin.signal_sources()`; remove the direct Phase-55
   wiring.
3. Add a second emitter from another domain to validate generality, e.g.:
   - `calendar` → upcoming high-salience events (meetings with tracked entities), or
   - a minimal `finance` source → large moves on watched tickers.
4. Container collects + registers all sources; admission gate consumes them uniformly.

---

## Dependencies

| Dependency | Purpose |
| ---------- | ------- |
| `ze_agents.plugin` | hook surface |
| `ze_memory` `Signal` | shared type (Phase 55) |
| Phase 56 admission | consumes polled signals |
| Phase 57 engine | owns source registration + cadence |

---

## Test Plan

- `collect_plugin_signal_sources` dedupes and raises on duplicate `source_key`.
- A plugin with no sources contributes none (default hook).
- News source emits `Signal`s equivalent to the Phase-55 direct path (parity test).
- Second-domain source emits signals that share entity resolution with news (cross-domain
  neighbourhood test: a calendar/finance signal and a news signal about the same org land
  in one neighbourhood).
- Admission gate receives signals from multiple sources in one cycle without engine
  changes.

---

## Open Questions

- [ ] Should `SignalSource` be pull-only for v1 simplicity, or define both `poll()` and an
  optional push channel now to avoid a later contract change?
- [ ] Where does the per-source `since` watermark live — in the engine, or owned by each
  source so plugins control their own replay semantics?
- [ ] Should magnitude normalization (Phase 56) be the source's responsibility (emit
  normalized 0..1) or the engine's (z-score across sources)? Affects this contract's shape.
- [ ] Do some sources need to emit *relationships* (not just events), e.g. "ticker X
  belongs to org Y", to seed the graph with structure plugins already know?
