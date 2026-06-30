# ADR: Single-user architecture

> **Status:** Accepted
> **Date:** 2023-11-01 (Phase 1)
> **Scope:** The entire system — data model, memory, routing, auth

---

## Context and Problem Statement

Ze is a personal AI assistant. The question is whether to build multi-tenant from day
one (a `user_id` column on every table, row-level isolation, per-user credential stores)
or to build for a single user and defer multi-tenancy. This is a foundational choice
that touches every table, every memory write, and the auth model.

---

## Decision Drivers

- Ze is explicitly a personal tool — the intended user is the person who deploys it
- Multi-tenancy adds complexity to every data access path (row-level security, credential
  isolation, billing, rate limiting per user)
- The memory and persona models are designed around a single person's continuity of
  experience — sharing them across users makes no conceptual sense
- Speed to value: the goal is a capable personal assistant, not a SaaS product

---

## Considered Options

1. **Multi-tenant from day one** — `user_id` foreign key on every table, per-user
   auth, credential stores partitioned by user
2. **Single-user, extract multi-tenant later** — build for one user, add tenant
   isolation if/when needed
3. **Single-user, never multi-tenant** — explicitly scope Ze as a self-hosted personal
   tool

---

## Decision Outcome

**Chosen option: Single-user (Option 2, leaning toward Option 3).**

No `user_id` column on any table. Authentication is a single `ZE_API_KEY` env var —
you either have it or you don't. Memory, persona, goals, and contacts are all
singleton resources. The system is designed to be deployed by one person for themselves.

### Positive Consequences

- No tenant isolation code anywhere — every query is simpler
- Memory and persona can be deeply personalised without partitioning
- Auth is a single env var check — no user accounts, sessions, or token rotation
- Data model is straightforward: all rows belong to "the user" implicitly

### Negative Consequences / Trade-offs

- Multi-tenant extraction would require adding `user_id` to every table,
  partitioning credentials and memory, and replacing the single-key auth model —
  a substantial rewrite
- Not suitable for deployment as a shared service without that rewrite
- No per-user rate limiting or cost attribution (though per-flow cost tracking exists)

---

## Pros and Cons of the Options

### Option 1 — Multi-tenant from day one

**Pros:** No migration needed if Ze ever serves multiple users.

**Cons:** Every table carries a `user_id`; every query filters by it; credential
stores partition per user; auth becomes a session system. All of this complexity is
wasted if Ze remains a personal tool.

### Option 2 / 3 — Single-user

**Pros:** Maximum simplicity. The data model reflects the conceptual reality: Ze
has one person it serves, and it knows everything about that person.

**Cons:** Hard to reverse. This is a deliberate bet that Ze remains personal.

---

## Links

- `apps/ze-api/ze_api/settings.py` — `ZE_API_KEY` as the sole auth mechanism
- `apps/ze-api/ze_api/api/` — `require_api_key` Depends
