# Phase 81 — Plugin NLI Adoption

**Status:** Done
**Depends on:** Phase 80 (NLIClient + DI)
**Packages touched:** `plugins/ze-news`, `plugins/ze-finance`

---

## What this is

Phase 80 made NLI available to all agents via `NLIClient` injection and optional
`nli_check_entailment` / `nli_grounding` tools. This phase applies NLI to the two
highest-value plugin gaps identified during Phase 80 planning: news semantic dedup
and finance merchant alias merging.

Each feature is behind a config flag so rollout can be gradual.

---

## News plugin

### 1. Headline–summary mismatch (credibility)

**File:** `plugins/ze-news/ze_news/credibility.py`

Today `headline_mismatch` is detected only in the LLM scoring pass. Add an NLI
heuristic pass before/alongside LLM:

- Premise = article summary, hypothesis = headline
- Flag when `contradiction ≥ 0.50` or `entailment < 0.30`

**Config:**

```yaml
news:
  nli_credibility_enabled: true
  nli_headline_contradiction_threshold: 0.50
  nli_headline_entailment_threshold: 0.30
```

### 2. Same-story clustering (semantic dedup)

**File:** `plugins/ze-news/ze_news/store.py` or post-`upsert()` in `jobs/fetch.py`

URL is the only dedup key today (see Phase 37). After upsert:

1. Cosine prefilter on recent articles (embedding ANN, same as `search()`)
2. Mutual entailment between summaries for pairs above cosine threshold
3. Cluster variants; keep highest-credibility article per cluster

**Config:**

```yaml
news:
  nli_dedup_enabled: true
  nli_dedup_cosine_threshold: 0.75
  nli_dedup_entailment_threshold: 0.70
```

### 3. Agent response grounding (optional)

**File:** `plugins/ze-news/ze_news/agents/agent.py`

After `agentic_loop`, verify agent paraphrase is entailed by source articles via
`nli_grounding`. Log or trim unsupported claims.

---

## Finance plugin

### 1. Merchant alias merging (recurring detection)

**File:** `plugins/ze-finance/ze_finance/recurring/detector.py`

Today grouping uses `_normalise(tx.notes)` exact match — misses `NETFLIX.COM` /
`Netflix` / `NETFLIX SUBSCRIPTION`.

Pre-grouping step:

1. Within `(currency, account_id)`, find description pairs with embedding cosine ≥ threshold
2. NLI confirm same merchant/service (`entailment ≥ 0.70`)
3. Merge groups before interval/amount analysis

**Config:**

```yaml
finance:
  nli_merchant_merge_enabled: true
  nli_merchant_cosine_threshold: 0.70
  nli_merchant_entailment_threshold: 0.70
```

### 2. Category inference fallback (lower priority)

**File:** `plugins/ze-finance/ze_finance/categoriser.py`

For unmatched descriptions, entailment against category exemplars before LLM batch.

---

## Wiring

Both plugins inject `NLIClient` via constructor DI (already in `dep_map` after Phase 80).

News agent tools (optional):

```python
deps={"nli_client": self._nli_client}
```

Add `ze_agents.nli_tools` to `agent_module_paths()` when agents declare NLI tools.

---

## Tests

| Test | Covers |
|---|---|
| `test_credibility_nli_headline_mismatch` | NLI flags stronger headline than summary |
| `test_news_cluster_dedup` | Two URLs, same story → one surfaced |
| `test_recurring_merchant_merge` | Variant descriptions → single recurring group |

---

## Implementation sequence

1. News NLI credibility pass (smallest diff, immediate value)
2. Finance merchant merge in `RecurringDetector`
3. News semantic clustering (requires store schema or metadata column for cluster_id)
4. Agent grounding checks (optional polish)
