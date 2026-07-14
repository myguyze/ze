# Feature Specification: Memory Retrieval Relevance

**Feature Branch**: `106-memory-retrieval-relevance`

**Created**: 2026-07-14

**Status**: Implemented

**Input**: User description: "Memory retrieval relevance — make ze-memory retrieval admit when nothing is relevant and use the existing graph topology as a first-class retrieval path. In scope: (1) return cosine similarity from all fact/episode/entity/event similarity queries, apply a tunable relevance floor, and surface the real similarity score (not extraction confidence) in MemoryChunkTrace / the Mind panel; (2) entity-anchored retrieval — extract salient entities from the query, match memory_entities by name/alias, pull related facts/episodes via graph edges (DESCRIBES, MENTIONS, SOURCED_FROM) and merge with vector candidates before budgeting; (3) composite ranking (similarity × recency decay × confidence) before token budgeting instead of raw ANN order; (4) NLI cross-encoder rerank of top fact candidates in the hot retrieval path (currently only session summaries + async cache). Out of scope / follow-up: swapping the embedding model for an asymmetric retrieval model — covered by phase 97."

## Problem Statement

Memory retrieval currently returns the top-K nearest neighbours for every query,
no matter how weak the match. Because there is no relevance floor, a question like
"why did the last trump workflow run fail?" injects five unrelated work notes into
the agent's context, and the Mind panel displays them with percentages that are
actually extraction confidence — not retrieval relevance — making the system look
arbitrary. Meanwhile, memories that name the queried entity directly (via the
existing entity/relationship graph) are never used as a retrieval entry point:
the graph only decorates results the vector search already picked.

## Clarifications

### Session 2026-07-14

- Q: Entity-anchored candidates need a relevance score comparable to vector cosine similarity for the floor and composite ranking (FR-009). How should that score be derived? → A: `score = max(vector_similarity, entity_match_constant)` — entity-only matches get a fixed high constant (guaranteeing they clear the floor per Story 2, even with mediocre embedding similarity); candidates found by both paths keep their true similarity when it exceeds the constant (keeping the Mind panel honest per FR-003). This is the same "strongest evidence wins" rule FR-008 already requires for dedup, applied uniformly to scoring.
- Q: How far should entity-anchored traversal walk from a matched entity across the DESCRIBES/MENTIONS/SOURCED_FROM edges? → A: One hop only — facts/episodes/events directly connected to the matched entity via a single edge. Matches the scenario language ("linked to it"), keeps latency bounded under SC-005, and avoids reintroducing the noise Story 1 removes.
- Q: Which retrieval policies are in scope for the full stack (floor, entity-anchored path, composite ranking, rerank) — conversational agents only, or all retrieval consumers including goal/workflow/prospecting/dream-memory domain services? → A: All retrieval consumers get the full stack in this phase, not just conversational agents. (Corrected during `/speckit-analyze`, 2026-07-14: "dream memory" and "workflow planning" were named in the original question as illustrative examples but do not correspond to real retrieval call sites — `core/ze-memory/ze_memory/dream/*` never calls the `RetrievalRequest`/policy architecture this phase changes, and `WorkflowPlanner` has no memory-retrieval call site at all. The intent — "all real retrieval consumers, not just conversational agents" — stands; FR-016 below lists only the retrieval consumers that actually exist in code.)
- Q: How should the new live-turn fact rerank (Story 4) relate to the existing async NLI cache used for session summaries (phase 79)? → A: Synchronous, uncached NLI call scoped to the small post-floor candidate set (bounded by FR-015) — a separate code path from the async session-summary cache, not a consumer of it.
- Q: Where should the relevance floor and composite-ranking weights (FR-002, FR-011) live — static `config.yaml` or a DB-backed override table? → A: `config/config.yaml`, consistent with existing structural config (models, schedules), hot-reloaded on SIGHUP. Not a DB-backed override — that pattern is reserved for feature gating (capability overrides), not tuning knobs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Irrelevant memories stay out of context (Priority: P1)

The user asks Ze a question for which no stored memory is genuinely relevant
(e.g. a question about a workflow whose details live only in the workflow store).
Ze retrieves nothing — or only memories above a relevance floor — instead of
padding the context with the least-unrelated facts it can find. The Mind panel
shows an honest picture: either "no relevant memories" or memories with a true
relevance score.

**Why this priority**: This is the observed defect. Irrelevant memories waste
tokens on every turn, can mislead agents, and destroy user trust in the memory
system when displayed. It is also the cheapest fix with the broadest effect —
every retrieval policy benefits.

**Independent Test**: Ask a question that matches no stored memory (verified by
inspecting the corpus). Confirm the memory block passed to the agent is empty
and the Mind panel reports no memories, while a question with a genuinely
relevant fact still retrieves it.

**Acceptance Scenarios**:

1. **Given** a memory corpus where no fact relates to the query topic, **When**
   the user asks about that topic, **Then** no facts below the relevance floor
   are included in the agent context.
2. **Given** a corpus containing at least one fact clearly about the query
   topic, **When** the user asks about it, **Then** that fact is retrieved and
   appears above the floor.
3. **Given** any retrieval, **When** the Mind panel displays memory chunks,
   **Then** each chunk shows the retrieval relevance score, not the extraction
   confidence.
4. **Given** the relevance floor is set too aggressively for a deployment,
   **When** the operator adjusts the configured threshold, **Then** the new
   floor takes effect without a code change.

---

### User Story 2 - Entity-named memories are found by name (Priority: P2)

The user asks about something by name — a workflow, a person, a project — and
Ze surfaces the memories linked to that named entity through the memory graph,
even when the query's embedding similarity to those memories is mediocre.

**Why this priority**: Names are the strongest retrieval signal a personal
assistant has, and the entity/relationship graph already exists but is unused
as an entry point. This fixes the "we have better-related memories than the
ones retrieved" class of failure.

**Independent Test**: Store a fact linked (via the graph) to a named entity.
Ask a question that mentions the entity by name or alias but is phrased so its
embedding is not close to the fact. Confirm the fact is retrieved.

**Acceptance Scenarios**:

1. **Given** an entity exists with linked facts and episodes, **When** the user's
   query mentions that entity's canonical name, **Then** those linked memories
   are included among the retrieval candidates before budgeting.
2. **Given** an entity is mentioned by a known alias rather than its canonical
   name, **When** the user asks about it, **Then** the alias resolves to the
   entity and its linked memories are candidates.
3. **Given** the same memory is found by both the vector path and the entity
   path, **When** candidates are merged, **Then** it appears once (deduplicated)
   and its ranking reflects the stronger evidence.
4. **Given** a query that mentions no known entity, **When** retrieval runs,
   **Then** behaviour is unchanged from vector-only retrieval (no errors, no
   spurious matches).

---

### User Story 3 - Best memories win the token budget (Priority: P2)

When more candidate memories exist than fit the context budget, the ones that
make it in are those that are most relevant, most recent, and most trustworthy —
not simply the nearest neighbours in arrival order.

**Why this priority**: The budget is filled in raw ANN order today, so one long
stale fact can crowd out a short, recent, highly relevant one. Ranking quality
determines what the agent actually sees.

**Independent Test**: Construct a corpus where an old low-confidence fact is
marginally nearer the query than a recent high-confidence fact, with a budget
that admits only one. Confirm the recent high-confidence fact wins.

**Acceptance Scenarios**:

1. **Given** two candidate facts of similar relevance where one is much more
   recent, **When** the budget admits only one, **Then** the recent one is
   selected.
2. **Given** two candidates of similar relevance and age where one has much
   higher confidence, **When** the budget admits only one, **Then** the
   higher-confidence one is selected.
3. **Given** a candidate set, **When** ranking is applied, **Then** the final
   order is deterministic and explainable from the per-candidate scores.

---

### User Story 4 - Semantic false positives are filtered before the agent sees them (Priority: P3)

Facts that are merely in the same broad semantic neighbourhood as the query
(e.g. "work stuff" for a question about a workflow failure) are demoted or
dropped by a deeper relevance check before the context is assembled, in the
retrieval paths agents use during live turns.

**Why this priority**: The relevance floor (Story 1) removes the worst noise,
but embedding similarity alone cannot distinguish "topically adjacent" from
"actually about this". The existing deeper relevance model is applied to
session summaries only; extending it to facts closes the gap. Lowest priority
because Stories 1–3 already remove most noise, and this adds per-turn latency
that must be controlled.

**Independent Test**: Craft a query plus a distractor fact that passes the
similarity floor but is not about the query subject, and a genuinely relevant
fact ranked below it by similarity. Confirm the rerank places the relevant
fact above the distractor.

**Acceptance Scenarios**:

1. **Given** fact candidates that pass the relevance floor, **When** the deeper
   relevance check runs in a live turn, **Then** candidates it judges irrelevant
   are demoted below genuinely relevant ones before budgeting.
2. **Given** the deeper relevance check is unavailable or times out, **When**
   retrieval runs, **Then** the turn completes using the floor-and-ranking
   result (graceful degradation, no user-facing failure).
3. **Given** the feature is disabled by configuration, **When** retrieval runs,
   **Then** behaviour matches Stories 1–3 only.

---

### Edge Cases

- Empty memory corpus: retrieval returns an empty context without errors.
- All candidates fall below the floor: the agent receives an empty memory block
  and the Mind panel communicates that no relevant memories were found (rather
  than showing nothing ambiguously).
- Memories stored without embeddings (legacy rows): they cannot pass a
  similarity floor; the existing recency fallback must not reintroduce
  unrelated facts above the floor semantics — legacy rows are only admitted
  through the entity-anchored path or until backfilled.
- Very short queries ("why?", "and then?") that embed poorly: the floor will
  likely exclude everything; conversation history — not memory — is expected to
  carry these turns.
- Entity names that are substrings of common words, or one entity's alias
  matching another entity's name: matching must be word-bounded and prefer the
  canonical name over alias collisions.
- Graph edges pointing at deleted/contradicted facts: the entity-anchored path
  must apply the same validity filters (not contradicted, retrievable) as the
  vector path.
- A retrieval-relevance score and an extraction-confidence score now coexist:
  introspection surfaces must label them distinctly so they are never conflated
  again.

## Requirements *(mandatory)*

### Functional Requirements

**Relevance floor & honest scores**

- **FR-001**: Every similarity-based memory lookup (facts, episodes, entities,
  events, session summaries) MUST compute and retain a normalized relevance
  score for each candidate, available to all downstream ranking, budgeting,
  and display steps.
- **FR-002**: Candidates whose relevance score falls below a configured floor
  MUST be excluded from the agent context. The floor MUST be configurable per
  deployment without a code change (via `config/config.yaml`, hot-reloaded on
  SIGHUP — consistent with existing structural config; not a DB-backed
  override), with a sensible default, and MUST be overridable per memory type
  if a single value proves wrong for one type.
- **FR-003**: The message trace and Mind panel MUST display the retrieval
  relevance score for each memory chunk. Extraction confidence MAY also be
  shown, but MUST be labelled distinctly.
- **FR-004**: When no memory passes the floor, the trace MUST record that
  retrieval ran and found nothing relevant (distinguishable from "retrieval
  did not run").

**Entity-anchored retrieval**

- **FR-005**: Retrieval MUST identify known entities mentioned in the query by
  matching canonical names and aliases (word-bounded, case-insensitive).
- **FR-006**: For each matched entity, retrieval MUST collect the facts,
  episodes, and events directly linked to it (one hop) through existing
  DESCRIBES / MENTIONS / SOURCED_FROM relationships and add them to the
  candidate pool before ranking and budgeting. Multi-hop traversal is out of
  scope.
- **FR-007**: Entity-anchored candidates MUST pass the same validity filters as
  vector candidates (not contradicted, retrievable, current-session exclusion).
- **FR-008**: Candidates found by both paths MUST be deduplicated, keeping the
  strongest relevance evidence.
- **FR-009**: Entity-anchored candidates MUST carry a relevance score compatible
  with the floor and composite ranking so the two paths merge into one ranked
  list. A direct name match constitutes strong relevance evidence: the score is
  `max(vector_similarity, entity_match_constant)`, where `entity_match_constant`
  is a configured value high enough to clear the relevance floor on its own, and
  `vector_similarity` is used instead whenever the same candidate was also found
  by the vector path with a higher score. This is the same "strongest evidence
  wins" rule as FR-008's dedup, applied to scoring rather than only to
  deduplication.

**Composite ranking**

- **FR-010**: Before token budgeting, candidates MUST be ordered by a composite
  score combining relevance, recency, and confidence — not by raw
  nearest-neighbour order.
- **FR-011**: The composite score's components and weights MUST be configurable
  (via `config/config.yaml`, hot-reloaded on SIGHUP), and each candidate's
  component scores MUST be inspectable (logged or traced) for tuning.
- **FR-012**: Token budgeting MUST consume candidates in composite-score order.

**Deep rerank in the live path**

- **FR-013**: The existing deeper relevance model (already used for session
  summaries) MUST be applicable to fact candidates during live-turn retrieval,
  gated by configuration. This is a synchronous, uncached call scoped to the
  small post-floor candidate set — a separate code path from the async cache
  used for session summaries, not a consumer of it.
- **FR-014**: The rerank step MUST degrade gracefully: if the model is
  unavailable, errors, or exceeds a time budget, retrieval proceeds with the
  floor-and-composite result.
- **FR-015**: The rerank MUST operate only on candidates that already passed
  the relevance floor, bounded to a configurable candidate count.

**Cross-cutting**

- **FR-016**: All retrieval policies that call the `RetrievalRequest`/policy
  architecture MUST apply the floor, entity-anchored path, composite ranking,
  and rerank — not conversational agents alone. This covers every
  orchestration-level policy (companion, research, email, prospecting, goals,
  workflow, calendar, reminders) and every domain-service-level policy
  (`PlannerPolicy`, called by `GoalPlanner`; `ToolExecutorPolicy`, called by
  `BaseAgent.agentic_loop` during goal/workflow tool execution).
  `MemoryUIPolicy`/`ProfilePolicy` (introspection) are exempt from the floor
  only, per their browsing intent. Dream memory's consolidation pipeline
  (`ze_memory/dream/*`) and `WorkflowPlanner` do not call this retrieval
  architecture today and are out of scope for this phase — should either
  start doing so, they inherit the same requirement as a follow-up, not a
  gap in this phase.
- **FR-017**: Existing behaviour MUST be recoverable via configuration
  (floor = 0, composite disabled ⇒ current ANN order) to allow safe rollout
  and A/B comparison via the eval suite.

### Key Entities

- **Memory candidate**: A fact, episode, entity, event, or session summary
  considered for inclusion; now carries a relevance score, a recency signal,
  a confidence value, and a provenance of which retrieval path found it.
- **Relevance floor**: A configured minimum relevance below which candidates
  are excluded; per-deployment, optionally per memory type.
- **Entity anchor**: A known entity matched in the query text by name or alias;
  the entry point for graph-linked candidate collection.
- **Composite score**: The ranking value combining relevance, recency decay,
  and confidence that determines budget order.
- **Memory chunk trace**: The per-chunk record shown in the Mind panel; now
  carries the true relevance score and its label.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For queries with no genuinely relevant stored memory (judged by
  a human or eval judge), the memory block delivered to the agent is empty in
  at least 90% of cases (today: ~0%).
- **SC-002**: For queries that name a known entity with linked memories, at
  least one linked memory appears in the delivered context in at least 90% of
  eval cases, even when phrasing is dissimilar to the stored text.
- **SC-003**: Every memory chunk displayed in the Mind panel shows a relevance
  score that matches the score used for selection; zero surfaces display
  extraction confidence as if it were relevance.
- **SC-004**: On the existing eval suite, answer quality does not regress:
  scenarios that previously passed still pass with the new retrieval defaults.
- **SC-005**: Median added latency of the full retrieval changes (floor +
  entity path + composite + rerank) is under 150 ms per turn with rerank
  enabled, and under 30 ms with rerank disabled.
- **SC-006**: Average memory tokens injected per turn decreases measurably
  (expected ≥ 30% reduction) without SC-004 regressing.

## Assumptions

- The existing entity/relationship graph (entities, DESCRIBES / MENTIONS /
  SOURCED_FROM edges) is populated well enough to serve as a retrieval entry
  point; no new extraction pipeline is in scope.
- The current embedding model stays as-is; its similarity distribution informs
  the default floor. The model swap is **phase 97 (Embedding Model Upgrade,
  Pending)** — the floor and score plumbing built here must be re-tuned, not
  redesigned, when phase 97 lands. Config-driven thresholds (FR-002, FR-011)
  are the mechanism for that re-tune.
- The deeper relevance model referred to in Story 4 is the existing local NLI
  cross-encoder (phase 79); no new model dependency is introduced.
- Relevance-floor and ranking-weight defaults will be tuned empirically against
  the existing eval scenarios plus new scenarios added for Stories 1–2; exact
  numeric defaults are an implementation-tuning concern, not a spec concern.
- Legacy rows without embeddings are rare and will be backfilled opportunistically;
  until then they are reachable only via the entity-anchored path.
- Single-user deployment; no multi-tenant ranking or privacy partitioning
  concerns.

## Follow-up (out of scope)

- **Embedding model upgrade** — swap `paraphrase-multilingual-MiniLM-L12-v2`
  for an asymmetric retrieval model (multilingual-e5) and embed facts as full
  predicate+value sentences. Already specced as
  [phase 97](../097-embedding-model-upgrade/spec.md); this phase's configurable
  floor and score plumbing are prerequisites for tuning that swap safely.
