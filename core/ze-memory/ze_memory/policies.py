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
from ze_memory.store import MemoryQueryable
from ze_memory.types import MemoryContext, RetrievalRequest


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


async def _fetch_events_by_similarity(conn: Any, emb: str, limit: int = 10) -> list:
    return await conn.fetch(
        """
        SELECT id, event_type, title, start_at, end_at,
               participant_names, participants, roles, summary, outcome, source_episode_id
        FROM memory_events
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )


async def _fetch_session_summary_rows(conn: Any, emb: str, limit: int = 10) -> list:
    return await conn.fetch(
        """
        SELECT id, session_id, summary, episode_count, last_turn_at,
               created_at, summary_updated_at
        FROM memory_session_summaries
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        emb,
        limit,
    )


# ── orchestration-level policies ──────────────────────────────────────────────

class CompanionPolicy:
    """Companion agent: facts + recent episodes + profile facets + entities + events."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY
                  CASE WHEN embedding IS NOT NULL
                       THEN embedding <=> $1::vector ELSE 1 END ASC,
                  updated_at DESC
                LIMIT 50
                """,
                emb,
            )
            episode_rows = await conn.fetch(
                f"""
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
                FROM memory_episodes
                WHERE embedding IS NOT NULL
                  AND ($2::text IS NULL OR session_id IS DISTINCT FROM $2)
                  AND session_id NOT IN (SELECT session_id FROM memory_session_summaries)
                  {episode_retrievable_sql()}
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                emb,
                cur_sid,
                EPISODES_FETCH_LIMIT,
            )
            profile_rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC LIMIT 30"
            )
            entity_rows = await conn.fetch(
                """
                SELECT id, entity_type, canonical_name, aliases, attrs
                FROM memory_entities
                ORDER BY
                  CASE WHEN embedding IS NOT NULL
                       THEN embedding <=> $1::vector ELSE 1 END ASC,
                  updated_at DESC
                LIMIT 20
                """,
                emb,
            )
            event_rows = await _fetch_events_by_similarity(conn, emb)
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        from ze_memory.projection import (
            budget_episodes, budget_facts, entities_from_rows, events_from_rows,
            facets_from_rows, session_summaries_from_rows, token_estimate,
        )
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS)
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        entities = entities_from_rows(entity_rows)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(facts=facts, episodes=episodes, session_summaries=session_summaries, profile=profile, entities=entities, events=events)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class ResearchPolicy:
    """Research agent: facts + broader episode window + events. No profile — research is topic-specific."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 30
                """,
                emb,
            )
            episode_rows = await conn.fetch(
                f"""
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
                FROM memory_episodes
                WHERE embedding IS NOT NULL
                  AND ($2::text IS NULL OR session_id IS DISTINCT FROM $2)
                  AND session_id NOT IN (SELECT session_id FROM memory_session_summaries)
                  {episode_retrievable_sql()}
                ORDER BY embedding <=> $1::vector
                LIMIT $3
                """,
                emb,
                cur_sid,
                EPISODES_FETCH_LIMIT,
            )
            event_rows = await _fetch_events_by_similarity(conn, emb)
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        from ze_memory.projection import budget_episodes, budget_facts, events_from_rows, session_summaries_from_rows, token_estimate
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(facts=facts, episodes=episodes, session_summaries=session_summaries, events=events)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class GoalsPolicy:
    """Goals agent: facts + profile facets + task state + events for the current goal."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 30
                """,
                emb,
            )
            profile_rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC LIMIT 30"
            )
            event_rows = await _fetch_events_by_similarity(conn, emb)

        task_state = await store.get_task_state(task_id=None, goal_id=request.goal_id)

        from ze_memory.projection import budget_facts, events_from_rows, facets_from_rows, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(facts=facts, profile=profile, task_state=task_state, events=events)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class WorkflowPolicy:
    """Workflow agent: minimal facts + task state for the current task."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )

        task_state = await store.get_task_state(task_id=request.task_id, goal_id=None)

        from ze_memory.projection import budget_facts, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, task_state=task_state)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class CalendarPolicy:
    """Calendar agent: minimal facts + conversation-extracted events."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )
            event_rows = await conn.fetch(
                """
                SELECT id, event_type, title, start_at, end_at,
                       participant_names, participants, roles, summary, outcome, source_episode_id
                FROM memory_events
                ORDER BY
                  CASE WHEN embedding IS NOT NULL
                       THEN embedding <=> $1::vector ELSE 1 END ASC,
                  COALESCE(start_at, created_at) DESC
                LIMIT 20
                """,
                emb,
            )

        from ze_memory.projection import budget_facts, events_from_rows, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(facts=facts, events=events)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class RemindersPolicy:
    """Reminders agent: minimal facts only — reminder state lives in its own store."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )

        from ze_memory.projection import budget_facts, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class EmailPolicy:
    """Email agent: facts + recent episodes + entities + events for correspondence context."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )
            episode_rows = await conn.fetch(
                f"""
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
                FROM memory_episodes
                WHERE embedding IS NOT NULL
                  AND ($2::text IS NULL OR session_id IS DISTINCT FROM $2)
                  AND session_id NOT IN (SELECT session_id FROM memory_session_summaries)
                  {episode_retrievable_sql()}
                ORDER BY embedding <=> $1::vector
                LIMIT 10
                """,
                emb,
                cur_sid,
            )
            entity_rows = await conn.fetch(
                """
                SELECT id, entity_type, canonical_name, aliases, attrs
                FROM memory_entities
                ORDER BY
                  CASE WHEN embedding IS NOT NULL
                       THEN embedding <=> $1::vector ELSE 1 END ASC,
                  updated_at DESC
                LIMIT 10
                """,
                emb,
            )
            event_rows = await _fetch_events_by_similarity(conn, emb)
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        from ze_memory.projection import (
            budget_episodes, budget_facts, entities_from_rows, events_from_rows,
            session_summaries_from_rows, token_estimate,
        )
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS)
        entities = entities_from_rows(entity_rows)
        events = events_from_rows(event_rows)
        ctx = MemoryContext(facts=facts, episodes=episodes, session_summaries=session_summaries, entities=entities, events=events)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


class ProspectingPolicy:
    """Prospecting agent: facts + recent episodes. Profile excluded — prospecting is outbound-focused."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)
        cur_sid = getattr(request, "current_session_id", None)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 30
                """,
                emb,
            )
            episode_rows = await conn.fetch(
                f"""
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
                FROM memory_episodes
                WHERE embedding IS NOT NULL
                  AND ($2::text IS NULL OR session_id IS DISTINCT FROM $2)
                  AND session_id NOT IN (SELECT session_id FROM memory_session_summaries)
                  {episode_retrievable_sql()}
                ORDER BY embedding <=> $1::vector
                LIMIT 10
                """,
                emb,
                cur_sid,
            )
            session_summary_rows = await _fetch_session_summary_rows(conn, emb)

        from ze_memory.projection import budget_episodes, budget_facts, session_summaries_from_rows, token_estimate
        from ze_memory.defaults import DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        session_summaries = session_summaries_from_rows(session_summary_rows, DEFAULT_SESSION_SUMMARY_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, episodes=episodes, session_summaries=session_summaries)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


# ── domain-service-level policies (called directly, not via fetch_context) ────

class PlannerPolicy:
    """Called directly by GoalPlanner before generating a milestone plan.

    Fetches facts + procedures (reusable patterns from past workflows) + task state
    for the current goal. Not dispatched via agent name.
    """

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 30
                """,
                emb,
            )
            proc_rows = await conn.fetch(
                """
                SELECT id, name, trigger, preconditions, steps, success_criteria,
                       version, source_refs
                FROM memory_procedures
                ORDER BY embedding <=> $1::vector
                LIMIT 10
                """,
                emb,
            )

        task_state = await store.get_task_state(task_id=None, goal_id=request.goal_id)

        from ze_memory.projection import budget_facts, procedures_from_rows, token_estimate

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

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                emb,
            )

        task_state = await store.get_task_state(
            task_id=request.task_id, goal_id=request.goal_id
        )

        from ze_memory.projection import budget_facts, token_estimate

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS)
        ctx = MemoryContext(facts=facts, task_state=task_state)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


# ── introspection policies ────────────────────────────────────────────────────

class ProfilePolicy:
    """Memory profile introspection (/memory profile): all profile facets + top facts."""

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                "SELECT id, subject_id, predicate, object_text, object_id, value,"
                " confidence, reviewed, contradicted, source_episode_id, source_refs"
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

    async def retrieve(self, request: RetrievalRequest, store: MemoryQueryable) -> MemoryContext:
        emb = _to_list(request.query_embedding)

        async with store.pool.acquire() as conn:
            fact_rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                ORDER BY updated_at DESC LIMIT 100
                """
            )
            episode_rows = await conn.fetch(
                f"""
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
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
            budget_episodes, budget_facts, entities_from_rows, facets_from_rows, token_estimate,
        )

        facts = budget_facts(fact_rows, DEFAULT_FACT_BUDGET_TOKENS * 3)
        episodes = budget_episodes(episode_rows, DEFAULT_EPISODE_BUDGET_TOKENS)
        profile = facets_from_rows(profile_rows, DEFAULT_PROFILE_BUDGET_TOKENS)
        entities = entities_from_rows(entity_rows)
        ctx = MemoryContext(facts=facts, episodes=episodes, profile=profile, entities=entities)
        ctx.token_estimate = token_estimate(ctx)
        return ctx


# ── registry ──────────────────────────────────────────────────────────────────

# Core-only policies (introspection + tool loop). Agent policies are contributed
# by plugins via ZePlugin.memory_policies().
_POLICY_MAP: dict[str, Any] = {
    "profile":       ProfilePolicy(),
    "memory_ui":     MemoryUIPolicy(),
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
            get_logger(__name__).warning("unknown_memory_module_fallback", module=module)
            return _FALLBACK_POLICY
        return self._policies[module]
