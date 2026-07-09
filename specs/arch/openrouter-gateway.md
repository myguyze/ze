# ADR: Use OpenRouter as the single LLM gateway

> **Status:** Accepted
> **Date:** 2023-11-01 (Phase 1)
> **Scope:** Every LLM call in the system — routing, agents, memory, critics, eval

---

## Context and Problem Statement

Ze needs to call multiple LLMs (cheap fast models for routing and haiku-class tasks,
expensive capable models for reasoning and synthesis). The question is how to wire those
calls — directly to each provider's SDK, or through a proxy.

---

## Decision Drivers

- Model selection will change frequently (new releases, price changes, capability jumps)
- We want a single billing line, not N separate API accounts
- Direct provider SDKs diverge: OpenAI, Anthropic, Gemini all have different interfaces
  and streaming contracts
- Ze is a personal assistant — cost visibility per-flow matters

---

## Considered Options

1. **Direct provider SDKs** — `anthropic`, `openai`, etc. called individually
2. **LiteLLM** — open-source proxy that normalises provider APIs
3. **OpenRouter only** — single endpoint, provider-agnostic model IDs

---

## Decision Outcome

**Chosen option: OpenRouter only.**

Single billing, a unified endpoint, and easy model swaps via config string.
`openrouter:web_search` also gives web search without a separate API key — the LLM
decides when to search, and it's billed the same way.

### Positive Consequences

- One API key, one billing dashboard
- Model swaps are a config change (`"anthropic/claude-sonnet-4-6"` → any other ID)
- `openrouter:web_search` server tool eliminates a separate search provider
- Cost per model/flow is visible in the OpenRouter dashboard and our own `CostTracker`

### Negative Consequences / Trade-offs

- Dependent on OpenRouter availability — if OpenRouter is down, Ze is down
- Provider-specific features not exposed through OpenRouter are unavailable
- Adds latency vs. direct calls (small but non-zero)
- OpenRouter's model IDs can lag behind provider releases by days

---

## Pros and Cons of the Options

### Option 1 — Direct provider SDKs

**Pros:** Lower latency, access to provider-specific features, no single point of failure.

**Cons:** N API keys, N billing dashboards, divergent streaming contracts, code changes
required to swap models.

### Option 2 — LiteLLM

**Pros:** Self-hosted proxy, normalised API, no vendor lock-in, fallback routing.

**Cons:** Infrastructure to run and maintain, adds ops complexity for a single-user
assistant; LiteLLM's async support has historically been incomplete.

### Option 3 — OpenRouter only

**Pros:** Zero infrastructure, single billing, simple config-driven model swaps.

**Cons:** External dependency; no access to provider-specific features; OpenRouter is
a commercial service that could change pricing or availability.

---

## Links

- [Phase 6 — OpenRouter Client](../phases/006-openrouter-client/spec.md)
- `core/ze-core/ze_core/openrouter/` — `OpenRouterClient` implementation
