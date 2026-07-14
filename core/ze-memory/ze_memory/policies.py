"""Module-specific retrieval policies.

Each policy decides which memory types to fetch and at what token budgets
for a given module. Policies are explicit code objects — not ad hoc branching
inside the store implementation.

Two tiers:

  Orchestration-level policies (dispatched via agent name in fetch_context node):
    companion, research, email, prospecting, goals, workflow, calendar, reminders
    + profile and memory_ui for introspection commands

  Domain-service-level policies (called directly by domain services mid-execution):
    planner — called by GoalPlanner before generating a milestone plan
    tool_executor — called by BaseAgent.agentic_loop() before each tool call

Every policy above (except MemoryUIPolicy/ProfilePolicy, which are introspection-only
and intentionally show broader context for browsing) selects a real cosine
`similarity` column for every embedding-ordered candidate and drops candidates
below `RelevanceConfig.floor` (or a per-type override) via `apply_relevance_floor()`
before budgeting (FR-002).
"""

from __future__ import annotations

from typing import Any

from ze_memory.defaults import (
    DEFAULT_EPISODE_BUDGET_TOKENS,
    DEFAULT_FACT_BUDGET_TOKENS,
    DEFAULT_PROCEDURE_BUDGET_TOKENS,
    DEFAULT_PROFILE_BUDGET_TOKENS,
    EPISODES_FETCH_LIMIT,
)
from ze_memory.dream.retrieval import episode_retrievable_sql
from ze_memory.relevance_config import RelevanceConfig, relevance_config
from ze_memory.store import MemoryQueryable
from ze_memory.types import MemoryContext, RetrievalRequest


# ── helpers ───────────────────────────────────────────────────────────────────

_FACT_SELECT = """
    SELECT id, subject_id, predicate, object_text, object_id, value,
           confidence, reviewed, contradicted, source_episode_id, source_refs,
           COALESCE(provenance, 'raw') AS provenance
"""

_ENTITY_SELECT = """
    SELECT id, entity_type, canonical_name, aliases, attrs
"""

_EPISODE_NO_SUMMARY = """
    AND NOT EXISTS (
        SELECT 1 FROM memory_session_summaries ss
        WHERE ss.session_id = memory_episodes.session_id
    )
"""


def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def _sim_col(param: str = "$1") -> str:
    """Real cosine similarity column, computed from the same distance used in ORDER BY."""
    return f"1 - (embedding <=> {param}::vector) AS similarity"


def apply_relevance_floor(
    rows: list[Any], memory_type: str, cfg: RelevanceConfig
) -> list[Any]:
    """Drop rows whose similarity is below the configured floor (or type override).

    `relevance_floor == 0` (or a resolved per-type override of 0) is the FR-017
    rollback path — every row passes through unchanged, matching pre-phase-106
    ANN-order behaviour, including rows with a NULL similarity (legacy rows with
    no embedding). Otherwise, a NULL similarity means "not eligible outside the
    entity-anchor path" and the row is dropped here.
    """
    threshold = cfg.floor_overrides.get(memory_type, cfg.floor)
    if threshold <= 0:
        return list(rows)
    kept = []
    for row in rows:
        sim = row.get("similarity") if hasattr(row, "get") else row["similarity"]
        if sim is None:
            continue
        if sim >= threshold:
            kept.append(row)
    return kept



async def _fetch_facts_by_similarity(conn: Any, emb: str, limit: int) -> list:
    rows = await conn.fetch(
        f"""
        {_FACT_SELECT}, {_sim_col()}
        FROM memory_facts
        WHERE contradicted = false AND embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )
    if len(rows) >= limit:
        return rows
    extra = await conn.fetch(
        f"""
        {_FACT_SELECT}, NULL::float8 AS similarity
        FROM memory_facts
        WHERE contradicted = false AND embedding IS NULL
        ORDER BY updated_at DESC
        LIMIT $1
        """,
        limit - len(rows),
    )
    return list(rows) + list(extra)


async def _fetch_entities_by_similarity(conn: Any, emb: str, limit: int) -> list:
    rows = await conn.fetch(
        f"""
        {_ENTITY_SELECT}, {_sim_col()}
        FROM memory_entities
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )
    if len(rows) >= limit:
        return rows
    extra = await conn.fetch(
        f"""
        {_ENTITY_SELECT}, NULL::float8 AS similarity
        FROM memory_entities
        WHERE embedding IS NULL
        ORDER BY updated_at DESC
        LIMIT $1
        """,
        limit - len(rows),
    )
    return list(rows) + list(extra)


async def _fetch_events_by_similarity(conn: Any, emb: str, limit: int = 10) -> list:
    return await conn.fetch(
        f"""
        SELECT id, event_type, title, start_at, end_at,
               participant_names, participants, roles, summary, outcome, source_episode_id,
               {_sim_col()}
        FROM memory_events
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )


async def _fetch_calendar_events_by_similarity(
    conn: Any, emb: str, limit: int = 20
) -> list:
    rows = await conn.fetch(
        f"""
        SELECT id, event_type, title, start_at, end_at,
               participant_names, participants, roles, summary, outcome, source_episode_id,
               {_sim_col()}
        FROM memory_events
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )
    if len(rows) >= limit:
        return rows
    extra = await conn.fetch(
        """
        SELECT id, event_type, title, start_at, end_at,
               participant_names, participants, roles, summary, outcome, source_episode_id,
               NULL::float8 AS similarity
        FROM memory_events
        WHERE embedding IS NULL
        ORDER BY COALESCE(start_at, created_at) DESC
        LIMIT $1
        """,
        limit - len(rows),
    )
    return list(rows) + list(extra)


async def _fetch_session_summary_rows(conn: Any, emb: str, limit: int = 10) -> list:
    return await conn.fetch(
        f"""
        SELECT id, session_id, summary, episode_count, last_turn_at,
               created_at, summary_updated_at, {_sim_col()}
        FROM memory_session_summaries
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )


def _episode_select(cur_sid_param: str, limit_param: str) -> str:
    return f"""
        SELECT id, session_id, agent, prompt, response, summary,
               relevance, created_at, linked_entity_ids, linked_fact_ids,
               {_sim_col()}
        FROM memory_episodes
        WHERE embedding IS NOT NULL
          AND ({cur_sid_param}::text IS NULL OR session_id IS DISTINCT FROM {cur_sid_param})
          {_EPISODE_NO_SUMMARY}
          {episode_retrievable_sql()}
        ORDER BY embedding <=> $1::vector
        LIMIT {limit_param}
    """


# ── orchestration-level policies ──────────────────────────────────────────────


class CompanionPolicy:
    """Companion agent: facts + recent episodes + profile facets + entities + events."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 50)
            episode_rows = await conn.fetch(
                _episode_select("$2", "$3"),
                emb,
                cur_sid,
                EPISODES_FETCH_LIMIT,
            )
            profile_rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC LIMIT 30"
            )
            entity_rows = await _fetch_entities_by_similarity(conn, emb, 20)
            event_rows = await _fetch_events_by_similarity(conn, emb)
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)
        episode_rows = apply_relevance_floor(episode_rows, "episode", cfg)
        entity_rows = apply_relevance_floor(entity_rows, "entity", cfg)
        event_rows = apply_relevance_floor(event_rows, "event", cfg)
        session_summary_rows = apply_relevance_floor(
            session_summary_rows, "session_summary", cfg
        )

        from ze_memory.projection import (
            budget_episodes,
            budget_facts,
            entities_from_rows,
            events_from_rows,
            facets_from_rows,
            session_summaries_from_rows,
            token_estimate,
        )
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(
            session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS
        )
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        entities = entities_from_rows(entity_rows)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(
            facts=facts,
            episodes=episodes,
            session_summaries=session_summaries,
            profile=profile,
            entities=entities,
            events=events,
        )
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class ResearchPolicy:
    """Research agent: facts + broader episode window + events. No profile — research is topic-specific."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                f"""
                {_FACT_SELECT}, {_sim_col()}
                FROM memory_facts
                WHERE contradicted = false AND embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT 30
                """,
                emb,
            )
            episode_rows = await conn.fetch(
                _episode_select("$2", "$3"),
                emb,
                cur_sid,
                EPISODES_FETCH_LIMIT,
            )
            event_rows = await _fetch_events_by_similarity(conn, emb)
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)
        episode_rows = apply_relevance_floor(episode_rows, "episode", cfg)
        event_rows = apply_relevance_floor(event_rows, "event", cfg)
        session_summary_rows = apply_relevance_floor(
            session_summary_rows, "session_summary", cfg
        )

        from ze_memory.projection import (
            budget_episodes,
            budget_facts,
            events_from_rows,
            session_summaries_from_rows,
            token_estimate,
        )
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(
            session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS
        )
        events = events_from_rows(event_rows)
        ctx = MemoryContext(
            facts=facts,
            episodes=episodes,
            session_summaries=session_summaries,
            events=events,
        )
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class GoalsPolicy:
    """Goals agent: facts + profile facets + task state + events for the current goal."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 30)
            profile_rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC LIMIT 30"
            )
            event_rows = await _fetch_events_by_similarity(conn, emb)

        task_state = await store.get_task_state(task_id=None, goal_id=request.goal_id)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)
        event_rows = apply_relevance_floor(event_rows, "event", cfg)

        from ze_memory.projection import (
            budget_facts,
            events_from_rows,
            facets_from_rows,
            token_estimate,
        )

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(
            facts=facts, profile=profile, task_state=task_state, events=events
        )
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class WorkflowPolicy:
    """Workflow agent: minimal facts + task state for the current task."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 20)

        task_state = await store.get_task_state(task_id=request.task_id, goal_id=None)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)

        from ze_memory.projection import budget_facts, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, task_state=task_state)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class CalendarPolicy:
    """Calendar agent: minimal facts + conversation-extracted events."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                f"""
                {_FACT_SELECT}, {_sim_col()}
                FROM memory_facts
                WHERE contradicted = false AND embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )
            event_rows = await _fetch_calendar_events_by_similarity(conn, emb)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)
        event_rows = apply_relevance_floor(event_rows, "event", cfg)

        from ze_memory.projection import budget_facts, events_from_rows, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(facts=facts, events=events)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class RemindersPolicy:
    """Reminders agent: minimal facts only — reminder state lives in its own store."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 20)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)

        from ze_memory.projection import budget_facts, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class EmailPolicy:
    """Email agent: facts + recent episodes + entities + events for correspondence context."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 20)
            episode_rows = await conn.fetch(
                _episode_select("$2", "10"),
                emb,
                cur_sid,
            )
            entity_rows = await _fetch_entities_by_similarity(conn, emb, 10)
            event_rows = await _fetch_events_by_similarity(conn, emb)
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)
        episode_rows = apply_relevance_floor(episode_rows, "episode", cfg)
        entity_rows = apply_relevance_floor(entity_rows, "entity", cfg)
        event_rows = apply_relevance_floor(event_rows, "event", cfg)
        session_summary_rows = apply_relevance_floor(
            session_summary_rows, "session_summary", cfg
        )

        from ze_memory.projection import (
            budget_episodes,
            budget_facts,
            entities_from_rows,
            events_from_rows,
            session_summaries_from_rows,
            token_estimate,
        )
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(
            session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS
        )
        entities = entities_from_rows(entity_rows)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(
            facts=facts,
            episodes=episodes,
            session_summaries=session_summaries,
            entities=entities,
            events=events,
        )
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class ProspectingPolicy:
    """Prospecting agent: facts + recent episodes. Profile excluded — prospecting is outbound-focused."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 30)
            episode_rows = await conn.fetch(
                _episode_select("$2", "10"),
                emb,
                cur_sid,
            )
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)
        episode_rows = apply_relevance_floor(episode_rows, "episode", cfg)
        session_summary_rows = apply_relevance_floor(
            session_summary_rows, "session_summary", cfg
        )

        from ze_memory.projection import (
            budget_episodes,
            budget_facts,
            session_summaries_from_rows,
            token_estimate,
        )
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(
            session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS
        )
        ctx = MemoryContext(
            facts=facts, episodes=episodes, session_summaries=session_summaries
        )
        ctx.token_estimate = token_estimate(ctx)
        return ctx


# ── domain-service-level policies (called directly, not via fetch_context) ────


class PlannerPolicy:
    """Called directly by GoalPlanner before generating a milestone plan.

    Fetches facts + procedures (reusable patterns from past workflows) + task state
    for the current goal. Not dispatched via agent name.
    """

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 30)
            proc_rows = await conn.fetch(
                """
                SELECT id, name, trigger, preconditions, steps, success_criteria,
                       version, source_refs
                FROM memory_procedures
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT 10
                """,
                emb,
            )

        task_state = await store.get_task_state(task_id=None, goal_id=request.goal_id)

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)

        from ze_memory.projection import (
            budget_facts,
            procedures_from_rows,
            token_estimate,
        )

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        procedures = procedures_from_rows(proc_rows, DEFAULT_PROCEDURE_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, procedures=procedures, task_state=task_state)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class ToolExecutorPolicy:
    """Called directly by BaseAgent.agentic_loop() before each tool call.

    Minimal fetch: only facts + task state. No episodes to keep context tight.
    Not dispatched via agent name.
    """

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cfg = relevance_config(store.settings)

        async with store.pool.acquire() as conn:
            fact_rows = await _fetch_facts_by_similarity(conn, emb, 20)

        task_state = await store.get_task_state(
            task_id=request.task_id, goal_id=request.goal_id
        )

        fact_rows = apply_relevance_floor(fact_rows, "fact", cfg)

        from ze_memory.projection import budget_facts, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, task_state=task_state)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


# ── introspection policies (exempt from the relevance floor, per FR-016) ──────


class ProfilePolicy:
    """Memory profile introspection (/memory profile): all profile facets + top facts."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                "SELECT id, subject_id, predicate, object_text, object_id, value,"
                " confidence, reviewed, contradicted, source_episode_id, source_refs,"
                " COALESCE(provenance, 'raw') AS provenance"
                " FROM memory_facts WHERE contradicted = false"
                " ORDER BY confidence DESC, updated_at DESC LIMIT 50"
            )
            profile_rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC"
            )

        from ze_memory.projection import budget_facts, facets_from_rows, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, profile=profile)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class MemoryUIPolicy:
    """Full memory UI display: all types at wider budgets."""

    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs,
                       COALESCE(provenance, 'raw') AS provenance
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY updated_at DESC LIMIT 100
                """
            )
            episode_rows = await conn.fetch(
                f"""
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids,
                       {_sim_col()}
                FROM memory_episodes
                WHERE embedding IS NOT NULL
                  {episode_retrievable_sql()}
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )
            profile_rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC"
            )
            entity_rows = await conn.fetch(
                "SELECT id, entity_type, canonical_name, aliases, attrs"
                " FROM memory_entities ORDER BY updated_at DESC LIMIT 50"
            )

        from ze_memory.projection import (
            budget_episodes,
            budget_facts,
            entities_from_rows,
            facets_from_rows,
            token_estimate,
        )

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS * 3)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        entities = entities_from_rows(entity_rows)
        ctx = MemoryContext(
            facts=facts, episodes=episodes, profile=profile, entities=entities
        )
        ctx.token_estimate = token_estimate(ctx)
        return ctx


# ── registry ──────────────────────────────────────────────────────────────────

# Core-only policies (introspection + tool loop). Agent policies are contributed
# by plugins via ZePlugin.memory_policies().
_POLICY_MAP: dict[str, Any] = {
    "profile": ProfilePolicy(),
    "memory_ui": MemoryUIPolicy(),
    "tool_executor": ToolExecutorPolicy(),
}


def collect_plugin_memory_policies(plugins: list[Any] | None) -> dict[str, Any]:
    """Merge memory_policies() from all plugins; raise on duplicate agent keys."""
    from ze_agents.errors import AgentConfigError

    merged: dict[str, Any] = {}
    for plugin in plugins or []:
        for module, policy in plugin.memory_policies().items():
            if module in merged:
                raise AgentConfigError(
                    f"Duplicate memory policy for agent {module!r}: "
                    f"{type(plugin).__name__} conflicts with an earlier plugin."
                )
            merged[module] = policy
    return merged


def build_policy_registry(plugins: list[Any] | None = None) -> DefaultPolicyRegistry:
    """Build a DefaultPolicyRegistry from core policies plus plugin contributions."""
    extra = collect_plugin_memory_policies(plugins)
    return DefaultPolicyRegistry(extra=extra)


_FALLBACK_POLICY = CompanionPolicy()


class DefaultPolicyRegistry:
    def __init__(self, extra: dict[str, Any] | None = None) -> None:
        self._policies = {**_POLICY_MAP, **(extra or {})}

    def register(self, module: str, policy: Any) -> None:
        self._policies[module] = policy

    def for_module(self, module: str) -> Any:
        if module not in self._policies:
            from ze_logging import get_logger

            get_logger(__name__).warning(
                "unknown_memory_module_fallback", module=module
            )
            return _FALLBACK_POLICY
        return self._policies[module]
