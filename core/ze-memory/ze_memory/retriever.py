from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ze_agents.logging import get_logger
from ze_agents.tasks import fire_and_forget
from ze_memory.consolidation_store import _cosine_similarity as _cosine_similarity  # noqa: F401

from ze_memory.defaults import (
    DEFAULT_EPISODE_BUDGET_TOKENS,
    DEFAULT_FACT_BUDGET_TOKENS,
    MODEL_SYNTHESIS,
)
from ze_memory.errors import InvalidRetrievalRequestError
from ze_memory.extractor import parse_fact_response, raw_to_facts
from ze_memory.graph.predicates import (
    BELONGS_TO_GOAL,
    DESCRIBES,
    MENTIONS,
    PARTICIPATES_IN,
    PROMOTES_TO,
    SOURCED_FROM,
)
from ze_memory.graph.store import GraphStore
from ze_memory.graph.traversal import BoundedExpansionPolicy
from ze_memory.graph.types import Relationship
from ze_memory.policies import DefaultPolicyRegistry
from ze_memory.projection import (
    budget_episodes,
    budget_facts,
    facets_from_rows,
    task_state_from_row,
)
from ze_memory.types import (
    Entity,
    EntityRef,
    Event,
    Fact,
    MemoryContext,
    Procedure,
    ProfileFacet,
    RetrievalRequest,
    Signal,
    SignalIngestResult,
    TaskState,
)

log = get_logger(__name__)

_EVENT_OUTCOME_SYSTEM = (
    "You extract generalizable declarative facts from an event outcome. "
    "Only extract durable learnings: preferences, decisions, patterns, or capabilities — "
    "not ephemeral or event-specific details. "
    "Return a JSON array — no markdown, just the array. "
    'Each item: {"predicate": "snake_case_label", "value": "the generalizable fact", "confidence": 0.0-1.0}. '
    "If no generalizable facts can be extracted, return []."
)


def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


class PostgresMemoryStore:
    def __init__(
        self,
        pool: Any,
        embedder: Any,
        openrouter_client: Any,
        settings: Any = None,
        policy_registry: Any = None,
        graph_store: GraphStore | None = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings
        self._registry = policy_registry or DefaultPolicyRegistry()
        self._graph_store = graph_store
        self._traversal = self._build_traversal(graph_store, settings)

    def apply_policy_registry(self, registry: Any) -> None:
        """Replace the retrieval policy registry (called after plugins are discovered)."""
        self._registry = registry

    @property
    def pool(self) -> Any:
        return self._pool

    # ── MemoryStore protocol ──────────────────────────────────────────────────

    async def retrieve(self, request: RetrievalRequest) -> MemoryContext:
        if not request.module:
            raise InvalidRetrievalRequestError("RetrievalRequest.module is required")
        if request.query_embedding is None:
            raise InvalidRetrievalRequestError("RetrievalRequest.query_embedding is required")

        policy = self._registry.for_module(request.module)
        ctx = await policy.retrieve(request, self)

        if self._traversal is not None:
            ctx = await self._graph_augment(ctx)

        return ctx

    async def _graph_augment(self, ctx: MemoryContext) -> MemoryContext:
        """Enrich MemoryContext via one-hop graph expansion from known entity/fact seeds."""
        from ze_memory.graph.projection import enrich_context

        seed_ids: list[UUID] = []
        for e in ctx.entities:
            if e.id is not None:
                seed_ids.append(e.id)
        for f in ctx.facts:
            if f.id is not None:
                seed_ids.append(f.id)

        if not seed_ids:
            return ctx

        try:
            expansion = await self._traversal.expand(seed_ids)
            return await enrich_context(ctx, expansion, self._pool)
        except Exception as exc:
            log.warning("graph_augmentation_failed", error=str(exc))
            return ctx

    async def write_episode(
        self,
        session_id: str,
        agent: str,
        prompt: str,
        response: str,
        embedding: Any,
    ) -> None:
        try:
            emb_list = _to_list(embedding)
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "INSERT INTO memory_episodes"
                    " (session_id, agent, prompt, response, embedding)"
                    " VALUES ($1, $2, $3, $4, $5::vector)"
                    " RETURNING id",
                    session_id,
                    agent,
                    prompt,
                    response,
                    emb_list,
                )
            episode_id: UUID = row["id"]
            if self._graph_store is not None:
                fire_and_forget(
                    self._link_episode_entities(episode_id, f"{prompt} {response}"),
                    label="link_episode_entities",
                )
        except Exception as exc:
            log.warning("memory_write_episode_failed", error=str(exc))

    async def propose_facts(self, proposals: list[Fact]) -> None:
        for fact in proposals:
            try:
                await self._write_fact_with_contradiction_check(fact)
            except Exception as exc:
                log.warning(
                    "memory_propose_fact_failed",
                    predicate=fact.predicate,
                    error=str(exc),
                )

    async def upsert_task_state(self, state: TaskState) -> None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_task_state
                  (task_id, goal_id, status, open_steps, blocked_by,
                   last_action, next_action, tool_cursors, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8::jsonb, NOW())
                ON CONFLICT (task_id) WHERE task_id IS NOT NULL DO UPDATE SET
                  status = EXCLUDED.status,
                  open_steps = EXCLUDED.open_steps,
                  blocked_by = EXCLUDED.blocked_by,
                  last_action = EXCLUDED.last_action,
                  next_action = EXCLUDED.next_action,
                  tool_cursors = EXCLUDED.tool_cursors,
                  updated_at = NOW()
                RETURNING id
                """,
                state.task_id,
                state.goal_id,
                state.status,
                json.dumps(state.open_steps),
                json.dumps(state.blocked_by),
                state.last_action,
                state.next_action,
                json.dumps(state.tool_cursors),
            )
        if self._graph_store is not None and state.goal_id is not None and row is not None:
            fire_and_forget(
                self._link_task_state_to_goal(row["id"], state.goal_id),
                label="link_task_state_to_goal",
            )

    async def propose_events(self, events: list[Event]) -> None:
        for event in events:
            try:
                resolved = await self._resolve_participant_names(event.participant_names)
                participants = list({*event.participants, *resolved})

                emb_list = (
                    _to_list(self._embedder.encode(event.title))
                    if self._embedder is not None else None
                )
                async with self._pool.acquire() as conn:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO memory_events
                          (event_type, title, start_at, end_at,
                           participant_names, participants, summary, outcome, embedding)
                        VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9::vector)
                        RETURNING id
                        """,
                        event.event_type,
                        event.title,
                        event.start_at,
                        event.end_at,
                        json.dumps(event.participant_names),
                        json.dumps([str(p) for p in participants]),
                        event.summary,
                        event.outcome,
                        emb_list,
                    )
                if self._graph_store is not None and participants:
                    fire_and_forget(
                        self._link_event_participants(row["id"], participants),
                        label="link_event_participants",
                    )
                if self._graph_store is not None and event.outcome:
                    fire_and_forget(
                        self._promote_event_outcome(row["id"], event.outcome),
                        label="promote_event_outcome",
                    )
            except Exception as exc:
                log.warning("memory_propose_event_failed", title=event.title, error=str(exc))

    async def propose_procedure(
        self,
        procedure: Procedure,
        linked_task_id: UUID | None = None,
        linked_task_type: str = "workflow",
    ) -> UUID | None:
        try:
            emb_list = (
                _to_list(self._embedder.encode(f"{procedure.trigger} {procedure.name}"))
                if self._embedder is not None else None
            )
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO memory_procedures
                      (name, trigger, preconditions, steps, success_criteria,
                       version, source_refs, embedding)
                    VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::jsonb, $6, $7::jsonb, $8::vector)
                    RETURNING id
                    """,
                    procedure.name,
                    procedure.trigger,
                    json.dumps(procedure.preconditions),
                    json.dumps(procedure.steps),
                    json.dumps(procedure.success_criteria),
                    procedure.version,
                    json.dumps([str(r) for r in procedure.source_refs]),
                    emb_list,
                )
            procedure_id: UUID = row["id"]
            if self._graph_store is not None and linked_task_id is not None:
                fire_and_forget(
                    self._link_procedure_to_task(procedure_id, linked_task_id, linked_task_type),
                    label="link_procedure_to_task",
                )
            return procedure_id
        except Exception as exc:
            log.warning("memory_propose_procedure_failed", name=procedure.name, error=str(exc))
            return None

    async def upsert_entity(self, entity: Entity) -> UUID:
        emb_list = (
            _to_list(self._embedder.encode(entity.canonical_name))
            if self._embedder is not None else None
        )
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_entities
                  (entity_type, canonical_name, aliases, attrs, embedding)
                VALUES ($1, $2, $3::jsonb, $4::jsonb, $5::vector)
                ON CONFLICT (lower(canonical_name)) DO UPDATE SET
                  aliases = EXCLUDED.aliases,
                  attrs = EXCLUDED.attrs,
                  embedding = COALESCE(EXCLUDED.embedding, memory_entities.embedding),
                  updated_at = NOW()
                RETURNING id
                """,
                entity.entity_type,
                entity.canonical_name.strip(),
                json.dumps(entity.aliases),
                json.dumps(entity.attrs),
                emb_list,
            )
        return row["id"]

    async def get_task_state(
        self,
        task_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> TaskState | None:
        if task_id is None and goal_id is None:
            return None
        async with self._pool.acquire() as conn:
            if task_id is not None:
                row = await conn.fetchrow(
                    "SELECT * FROM memory_task_state WHERE task_id = $1", task_id
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM memory_task_state WHERE goal_id = $1"
                    " ORDER BY updated_at DESC LIMIT 1",
                    goal_id,
                )
        if row is None:
            return None
        return task_state_from_row(row)

    async def get_profile(self) -> list[ProfileFacet]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC"
            )
        return facets_from_rows(rows, budget_tokens=10_000)

    # ── convenience methods for jobs/introspection ────────────────────────────

    async def list_recent_facts(self, days: int, limit: int) -> list[Fact]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                  AND updated_at >= now() - ($1 || ' days')::interval
                ORDER BY confidence DESC, updated_at DESC
                LIMIT $2
                """,
                str(days),
                limit,
            )
        return budget_facts(rows, DEFAULT_FACT_BUDGET_TOKENS * 20)

    async def list_recent_episodes(self, days: int, limit: int) -> list[Any]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
                FROM memory_episodes
                WHERE created_at >= now() - ($1 || ' days')::interval
                ORDER BY created_at DESC
                LIMIT $2
                """,
                str(days),
                limit,
            )
        return budget_episodes(rows, DEFAULT_EPISODE_BUDGET_TOKENS * 20)

    # ── internal ──────────────────────────────────────────────────────────────

    async def _write_fact_with_contradiction_check(self, fact: Fact) -> UUID | None:
        value_emb = self._embedder.encode(fact.value)
        emb_list = _to_list(value_emb)

        async with self._pool.acquire() as conn:
            # Invalidate prior facts for the same (predicate, subject).
            # IS NOT DISTINCT FROM handles NULL subject_id correctly.
            await conn.execute(
                """
                UPDATE memory_facts
                   SET contradicted = true
                 WHERE predicate = $1
                   AND subject_id IS NOT DISTINCT FROM $2
                   AND contradicted = false
                """,
                fact.predicate,
                fact.subject_id,
            )

            row = await conn.fetchrow(
                "INSERT INTO memory_facts"
                " (subject_id, predicate, object_text, object_id, value,"
                "  confidence, reviewed, contradicted,"
                "  source_episode_id, source_refs, embedding)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::vector)"
                " RETURNING id",
                fact.subject_id,
                fact.predicate,
                fact.object_text,
                fact.object_id,
                fact.value,
                fact.confidence,
                fact.reviewed,
                fact.contradicted,
                fact.source_episode_id,
                json.dumps([str(r) for r in fact.source_refs]),
                emb_list,
            )
            fact_id: UUID = row["id"]

        if self._graph_store is not None:
            fire_and_forget(
                self._link_fact_relationships(fact, fact_id),
                label="link_fact_relationships",
            )
        return fact_id

    # ── graph relationship helpers ─────────────────────────────────────────────

    async def _link_fact_relationships(self, fact: Fact, fact_id: UUID) -> None:
        """Create entity→fact (DESCRIBES) and fact→episode (SOURCED_FROM) edges."""
        try:
            if fact.subject_id is not None:
                await self._graph_store.upsert_relationship(Relationship(
                    source_id=fact.subject_id,
                    source_type="entity",
                    predicate=DESCRIBES,
                    target_id=fact_id,
                    target_type="fact",
                    provenance_id=fact.source_episode_id,
                    creation_method="extracted",
                    confidence=fact.confidence,
                ))
            if fact.source_episode_id is not None:
                await self._graph_store.upsert_relationship(Relationship(
                    source_id=fact_id,
                    source_type="fact",
                    predicate=SOURCED_FROM,
                    target_id=fact.source_episode_id,
                    target_type="episode",
                    creation_method="explicit",
                ))
        except Exception as exc:
            log.warning("graph_link_fact_failed", fact_predicate=fact.predicate, error=str(exc))

    async def _link_episode_entities(self, episode_id: UUID, text: str) -> None:
        """Scan episode text for entity name/alias matches; write MENTIONS edges and update linked_entity_ids."""
        try:
            text_lower = text.lower()
            async with self._pool.acquire() as conn:
                entity_rows = await conn.fetch(
                    """
                    SELECT id
                    FROM memory_entities
                    WHERE position(lower(canonical_name) in $1) > 0
                       OR EXISTS (
                           SELECT 1 FROM jsonb_array_elements_text(aliases) AS alias
                           WHERE position(lower(alias) in $1) > 0
                       )
                    """,
                    text_lower,
                )

            matched_ids: list[UUID] = [row["id"] for row in entity_rows]
            if not matched_ids:
                return

            async with self._pool.acquire() as conn:
                await conn.execute(
                    "UPDATE memory_episodes SET linked_entity_ids = $1::jsonb WHERE id = $2",
                    json.dumps([str(eid) for eid in matched_ids]),
                    episode_id,
                )

            for entity_id in matched_ids:
                await self._graph_store.upsert_relationship(Relationship(
                    source_id=episode_id,
                    source_type="episode",
                    predicate=MENTIONS,
                    target_id=entity_id,
                    target_type="entity",
                    creation_method="extracted",
                    confidence=0.8,
                ))
        except Exception as exc:
            log.warning("graph_link_episode_entities_failed", episode_id=str(episode_id), error=str(exc))

    async def _link_event_participants(self, event_id: UUID, participant_ids: list[UUID]) -> None:
        """Create PARTICIPATES_IN edges from an event to each participant entity."""
        try:
            for entity_id in participant_ids:
                await self._graph_store.upsert_relationship(Relationship(
                    source_id=event_id,
                    source_type="event",
                    predicate=PARTICIPATES_IN,
                    target_id=entity_id,
                    target_type="entity",
                    creation_method="explicit",
                ))
        except Exception as exc:
            log.warning("graph_link_event_participants_failed", event_id=str(event_id), error=str(exc))

    async def _link_procedure_to_task(
        self, procedure_id: UUID, task_id: UUID, task_type: str
    ) -> None:
        """Create USES_PROCEDURE edge from a stored procedure to the goal/workflow that produced it."""
        try:
            from ze_memory.graph.predicates import USES_PROCEDURE
            await self._graph_store.upsert_relationship(Relationship(
                source_id=procedure_id,
                source_type="procedure",
                predicate=USES_PROCEDURE,
                target_id=task_id,
                target_type=task_type,
                creation_method="explicit",
            ))
        except Exception as exc:
            log.warning(
                "graph_link_procedure_failed",
                procedure_id=str(procedure_id),
                error=str(exc),
            )

    async def _link_task_state_to_goal(self, task_state_id: UUID, goal_id: UUID) -> None:
        """Create BELONGS_TO_GOAL edge from task state to its goal."""
        try:
            await self._graph_store.upsert_relationship(Relationship(
                source_id=task_state_id,
                source_type="task_state",
                predicate=BELONGS_TO_GOAL,
                target_id=goal_id,
                target_type="goal",
                creation_method="explicit",
            ))
        except Exception as exc:
            log.warning("graph_link_task_state_failed", task_state_id=str(task_state_id), error=str(exc))

    async def _resolve_entity_ref(
        self,
        ref: EntityRef,
        existing: dict[str, UUID],
    ) -> UUID | None:
        """Look up or create an entity for a typed EntityRef, updating the shared cache."""
        lower = ref.name.strip().lower()
        if not lower or len(lower) < 2:
            return None
        if lower in existing:
            return existing[lower]
        try:
            entity_id = await self.upsert_entity(Entity(
                id=None,
                entity_type=ref.entity_type,
                canonical_name=ref.name.strip(),
                aliases=[],
                attrs={},
            ))
            existing[lower] = entity_id
            return entity_id
        except Exception as exc:
            log.warning("entity_ref_upsert_failed", name=ref.name, type=ref.entity_type, error=str(exc))
            return None

    async def _resolve_participant_names(self, names: list[str]) -> list[UUID]:
        """Resolve participant name strings to entity UUIDs, auto-creating when unmatched."""
        if not names:
            return []
        _GENERIC = frozenset({"the", "a", "an", "all", "everyone", "team", "group", "us", "we", "they", "them"})

        candidates: list[str] = []
        for raw in names:
            name = raw.strip()
            lower = name.lower()
            if not name or len(name) < 2:
                continue
            if lower in _GENERIC or any(w.lower() in _GENERIC for w in name.split()):
                continue
            candidates.append(name)

        if not candidates:
            return []

        lower_candidates = [c.lower() for c in candidates]

        async with self._pool.acquire() as conn:
            entity_rows = await conn.fetch(
                """
                SELECT id, canonical_name, aliases
                FROM memory_entities
                WHERE lower(canonical_name) = ANY($1)
                   OR EXISTS (
                       SELECT 1 FROM jsonb_array_elements_text(aliases) AS alias
                       WHERE lower(alias) = ANY($1)
                   )
                """,
                lower_candidates,
            )

        existing: dict[str, UUID] = {}
        for row in entity_rows:
            existing[row["canonical_name"].lower()] = row["id"]
            for alias in (row["aliases"] or []):
                if alias:
                    existing[alias.lower()] = row["id"]

        resolved: list[UUID] = []
        for name in candidates:
            entity_id = await self._resolve_entity_ref(
                EntityRef(name=name, entity_type="person"),
                existing,
            )
            if entity_id is not None:
                resolved.append(entity_id)
        return resolved

    async def _promote_event_outcome(self, event_id: UUID, outcome: str) -> None:
        """Extract generalizable facts from an event outcome and link them via PROMOTES_TO edges."""
        if self._client is None or self._graph_store is None:
            return
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": f"Event outcome: {outcome}"}],
                model=self._synthesis_model(),
                system=_EVENT_OUTCOME_SYSTEM,
                max_tokens=300,
            )
            facts = raw_to_facts(parse_fact_response(raw))
            for fact in facts:
                try:
                    fact_id = await self._write_fact_with_contradiction_check(fact)
                    if fact_id is not None:
                        await self._graph_store.upsert_relationship(Relationship(
                            source_id=event_id,
                            source_type="event",
                            predicate=PROMOTES_TO,
                            target_id=fact_id,
                            target_type="fact",
                            creation_method="extracted",
                            confidence=fact.confidence,
                        ))
                except Exception as exc:
                    log.warning("graph_promote_event_outcome_fact_failed", error=str(exc))
            log.info("graph_promote_event_outcome_done", event_id=str(event_id), facts=len(facts))
        except Exception as exc:
            log.warning("graph_promote_event_outcome_failed", event_id=str(event_id), error=str(exc))

    async def _generate_summary(self, episode_id: Any, prompt: str, response: str) -> str | None:
        try:
            return await self._client.complete(
                messages=[{
                    "role": "user",
                    "content": (
                        "Summarize this interaction in one sentence.\n"
                        f"User: {prompt}\nAssistant: {response}"
                    ),
                }],
                model=self._synthesis_model(),
                max_tokens=100,
            )
        except Exception as exc:
            log.warning(
                "memory_summary_generation_failed",
                episode_id=str(episode_id),
                error=str(exc),
            )
            return None

    async def upsert_profile_facets(self, facets: list[dict]) -> None:
        async with self._pool.acquire() as conn:
            for facet in facets:
                await conn.execute(
                    """
                    INSERT INTO memory_profile_facets (key, value, stability, confidence, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (key) DO UPDATE SET
                      value = EXCLUDED.value,
                      stability = EXCLUDED.stability,
                      confidence = EXCLUDED.confidence,
                      updated_at = NOW()
                    """,
                    facet["key"],
                    facet["value"],
                    facet.get("stability", "dynamic"),
                    facet.get("confidence", 0.8),
                )

    async def ingest_signal(self, signal: Signal) -> SignalIngestResult | None:
        """Resolve entities, write a Signal node, create MENTIONS edges.

        Returns None on unexpected error; returns result with created=False when deduped.
        """
        try:
            async with self._pool.acquire() as conn:
                existing_row = await conn.fetchrow(
                    "SELECT id FROM memory_signals WHERE source = $1 AND external_ref = $2",
                    signal.source,
                    signal.external_ref,
                )
                if existing_row is not None:
                    return SignalIngestResult(
                        signal_id=existing_row["id"],
                        entity_ids=[],
                        created=False,
                    )

                row = await conn.fetchrow(
                    """
                    INSERT INTO memory_signals
                      (id, source, external_ref, title, summary, occurred_at,
                       magnitude, payload, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                    RETURNING id
                    """,
                    signal.id,
                    signal.source,
                    signal.external_ref,
                    signal.title,
                    signal.summary,
                    signal.occurred_at,
                    signal.magnitude,
                    json.dumps(signal.payload),
                    signal.expires_at,
                )
            signal_id: UUID = row["id"]

            entity_ids: list[UUID] = []
            if self._graph_store is not None and signal.entities:
                existing_cache: dict[str, UUID] = {}
                for ref in signal.entities:
                    entity_id = await self._resolve_entity_ref(ref, existing_cache)
                    if entity_id is not None:
                        entity_ids.append(entity_id)
                        try:
                            await self._graph_store.upsert_relationship(Relationship(
                                source_id=signal_id,
                                source_type="signal",
                                predicate=MENTIONS,
                                target_id=entity_id,
                                target_type="entity",
                                creation_method="extracted",
                                confidence=0.9,
                            ))
                        except Exception as exc:
                            log.warning(
                                "signal_entity_edge_failed",
                                signal_id=str(signal_id),
                                entity_id=str(entity_id),
                                error=str(exc),
                            )

            log.info(
                "signal_ingested",
                signal_id=str(signal_id),
                source=signal.source,
                entities=len(entity_ids),
            )
            return SignalIngestResult(signal_id=signal_id, entity_ids=entity_ids, created=True)
        except Exception as exc:
            log.warning("signal_ingest_failed", external_ref=signal.external_ref, error=str(exc))
            return None

    @staticmethod
    def _build_traversal(
        graph_store: GraphStore | None,
        settings: Any,
    ) -> BoundedExpansionPolicy | None:
        if graph_store is None:
            return None
        graph_cfg: dict = {}
        cfg = getattr(settings, "config", None)
        if isinstance(cfg, dict):
            graph_cfg = cfg.get("memory", {}).get("graph", {})
        elif isinstance(settings, dict):
            graph_cfg = settings.get("memory", {}).get("graph", {})
        if not graph_cfg.get("enabled", True):
            return None
        return BoundedExpansionPolicy(
            graph_store=graph_store,
            max_hops=int(graph_cfg.get("max_hops", 1)),
            limit=int(graph_cfg.get("max_relationships", 20)),
        )

    def _memory_config(self) -> dict:
        if self._settings is None:
            return {}
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("memory", {})
        if isinstance(self._settings, dict):
            return self._settings.get("memory", {})
        return {}

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
