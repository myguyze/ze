from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ze_logging import get_logger
from ze_memory.dream.scorer import replay_score as compute_replay_score
from ze_memory.dream.types import ArtifactType

log = get_logger(__name__)

_DEFAULT_MAX_REPLAY = 100
_DEFAULT_DECAY_CYCLES = 5
_DEFAULT_DECAY_RATE = 0.1
_DEFAULT_FORGETTING_THRESHOLD = 0.1
_DEFAULT_MAX_SCHEMA_CANDIDATES = 30
_DEFAULT_ARCHIVE_THRESHOLD_DAYS = 7


class SleepPass:
    def __init__(
        self,
        pool: Any,
        embedder: Any,
        consolidator: Any,
        dream_store: Any,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._consolidator = consolidator
        self._dream_store = dream_store
        self._settings = settings

    async def run(self, run_id: Any) -> dict:
        start = time.monotonic()
        cfg = self._config()

        episodes_scored = await self._score_refresh()
        episodes_replayed = await self._select_replay_candidates(cfg)
        await self._consolidator.archive_session_episodes()
        await self._consolidator.dedup_facts()
        await self._decay_pass(cfg)
        schema_candidates = await self._detect_schema_candidates(run_id, cfg)
        policy_candidates = await self._detect_policy_candidates(run_id, cfg)

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "sleep_pass_complete",
            episodes_scored=episodes_scored,
            episodes_replayed=episodes_replayed,
            schema_candidates=schema_candidates,
            policy_candidates=policy_candidates,
            duration_ms=duration_ms,
        )
        return {
            "episodes_scored": episodes_scored,
            "episodes_replayed": episodes_replayed,
            "schema_candidates": schema_candidates,
            "policy_candidates": policy_candidates,
            "duration_ms": duration_ms,
        }

    async def _score_refresh(self) -> int:
        now = datetime.now(tz=timezone.utc)
        async with self._pool.acquire() as conn:
            episodes = await conn.fetch(
                """
                SELECT
                    ep.id, ep.session_id, ep.relevance, ep.created_at, ep.embedding,
                    em.replay_count, em.source, em.has_sensitive_entity
                FROM memory_episodes ep
                LEFT JOIN memory_episode_metadata em ON em.episode_id = ep.id
                WHERE ep.summary IS NULL
                  AND ep.created_at > now() - interval '30 days'
                ORDER BY ep.created_at DESC
                LIMIT 500
                """
            )

            facts = await conn.fetch(
                "SELECT id, embedding FROM memory_facts"
                " WHERE contradicted = false AND embedding IS NOT NULL"
                " LIMIT 200"
            )

        fact_embeddings = [r["embedding"] for r in facts if r["embedding"] is not None]

        scored = 0
        for ep in episodes:
            has_sensitive = await self._check_sensitive_entities(ep["id"])
            source = ep["source"] or "ze_observed"

            class _EpProxy:
                pass

            proxy = _EpProxy()
            proxy.has_sensitive_entity = has_sensitive
            proxy.relevance = ep["relevance"] or 0.0
            proxy.created_at = ep["created_at"]
            proxy.replay_count = ep["replay_count"] or 0
            proxy.source = source
            proxy.embedding = ep["embedding"]

            class _FactProxy:
                pass

            class _FactProxyWithEmb:
                def __init__(self, emb):
                    self.embedding = emb

            fact_proxies = [_FactProxyWithEmb(e) for e in fact_embeddings]
            score = compute_replay_score(proxy, now, fact_proxies)

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO memory_episode_metadata
                        (episode_id, replay_score, source, has_sensitive_entity, updated_at)
                    VALUES ($1, $2, $3, $4, now())
                    ON CONFLICT (episode_id) DO UPDATE SET
                        replay_score         = EXCLUDED.replay_score,
                        has_sensitive_entity = EXCLUDED.has_sensitive_entity,
                        updated_at           = now()
                    """,
                    ep["id"],
                    score,
                    source,
                    has_sensitive,
                )
            scored += 1

        return scored

    async def _check_sensitive_entities(self, episode_id: Any) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1
                FROM memory_entities ent
                WHERE ent.sensitive = true
                  AND ent.id::text = ANY(
                    SELECT jsonb_array_elements_text(ep.linked_entity_ids)
                    FROM memory_episodes ep WHERE ep.id = $1
                  )
                LIMIT 1
                """,
                episode_id,
            )
        return row is not None

    async def _select_replay_candidates(self, cfg: dict) -> int:
        max_replay = int(cfg.get("max_replay_episodes", _DEFAULT_MAX_REPLAY))
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT episode_id FROM memory_episode_metadata
                WHERE has_sensitive_entity = FALSE
                  AND replay_score IS NOT NULL
                ORDER BY replay_score DESC
                LIMIT $1
                """,
                max_replay,
            )
            if not rows:
                return 0
            ids = [r["episode_id"] for r in rows]
            await conn.execute(
                """
                UPDATE memory_episode_metadata SET
                    replay_count     = replay_count + 1,
                    last_replayed_at = now(),
                    updated_at       = now()
                WHERE episode_id = ANY($1::uuid[])
                """,
                ids,
            )
        return len(ids)

    async def _decay_pass(self, cfg: dict) -> None:
        decay_cycles = int(cfg.get("decay_cycles", _DEFAULT_DECAY_CYCLES))
        decay_rate = float(cfg.get("decay_rate", _DEFAULT_DECAY_RATE))
        forgetting_threshold = float(cfg.get("forgetting_weight_threshold", _DEFAULT_FORGETTING_THRESHOLD))

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_episode_metadata SET
                    retrieval_weight = GREATEST(0.0, retrieval_weight - $1),
                    provenance = CASE
                        WHEN GREATEST(0.0, retrieval_weight - $1) <= $2 THEN 'archived'
                        ELSE provenance
                    END,
                    updated_at = now()
                WHERE retrieval_weight > $2
                  AND provenance != 'archived'
                  AND (
                    last_replayed_at IS NULL
                    OR last_replayed_at < now() - ($3 || ' days')::interval
                  )
                """,
                decay_rate,
                forgetting_threshold,
                str(decay_cycles),
            )

    async def _detect_schema_candidates(self, run_id: Any, cfg: dict) -> int:
        max_candidates = int(cfg.get("max_schema_candidates_per_run", _DEFAULT_MAX_SCHEMA_CANDIDATES))

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    e.id AS entity_id,
                    e.canonical_name,
                    array_agg(DISTINCT ep.session_id) AS sessions,
                    array_agg(DISTINCT ep.id) AS episode_ids,
                    count(DISTINCT ep.session_id) AS session_count
                FROM memory_entities e
                JOIN memory_episodes ep
                    ON ep.linked_entity_ids::jsonb ? e.id::text
                JOIN memory_episode_metadata em
                    ON em.episode_id = ep.id
                LEFT JOIN memory_session_summaries ss
                    ON ss.session_id = ep.session_id
                WHERE em.has_sensitive_entity = FALSE
                  AND e.sensitive = FALSE
                  AND (ss.dream_influenced = FALSE OR ss.dream_influenced IS NULL)
                GROUP BY e.id, e.canonical_name
                HAVING count(DISTINCT ep.session_id) >= 3
                ORDER BY count(DISTINCT ep.session_id) DESC
                LIMIT $1
                """,
                max_candidates,
            )

        saved = 0
        for row in rows:
            sessions = list(row["sessions"]) if row["sessions"] else []
            episode_ids = list(row["episode_ids"]) if row["episode_ids"] else []
            content = (
                f"Schema candidate: entity '{row['canonical_name']}' "
                f"appears across {row['session_count']} distinct sessions."
            )
            try:
                await self._dream_store.save_artifact(
                    run_id=run_id,
                    artifact_type=ArtifactType.SCHEMA_CANDIDATE.value,
                    content=content,
                    source_episode_ids=episode_ids,
                    source_fact_ids=[],
                    support_count=len(episode_ids),
                    distinct_session_count=len(sessions),
                    temporal_spread_days=0,
                    user_asserted_source_count=0,
                )
                saved += 1
            except Exception as exc:
                log.warning(
                    "schema_candidate_save_failed",
                    entity=row["canonical_name"],
                    error=str(exc),
                )

        return saved

    async def _detect_policy_candidates(self, run_id: Any, cfg: dict) -> int:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    ep.agent,
                    array_agg(DISTINCT ep.session_id) AS sessions,
                    array_agg(DISTINCT ep.id) AS episode_ids,
                    count(DISTINCT ep.session_id) AS session_count
                FROM memory_episodes ep
                JOIN memory_episode_metadata em ON em.episode_id = ep.id
                LEFT JOIN memory_session_summaries ss ON ss.session_id = ep.session_id
                WHERE em.has_sensitive_entity = FALSE
                  AND em.source = 'ze_observed'
                  AND ep.summary IS NULL
                  AND (ss.dream_influenced = FALSE OR ss.dream_influenced IS NULL)
                GROUP BY ep.agent
                HAVING count(DISTINCT ep.session_id) >= 3
                ORDER BY count(DISTINCT ep.session_id) DESC
                LIMIT 10
                """
            )

        saved = 0
        for row in rows:
            sessions = list(row["sessions"]) if row["sessions"] else []
            episode_ids = list(row["episode_ids"]) if row["episode_ids"] else []
            content = (
                f"Policy candidate: agent '{row['agent']}' "
                f"has been active across {row['session_count']} distinct sessions."
            )
            try:
                await self._dream_store.save_artifact(
                    run_id=run_id,
                    artifact_type=ArtifactType.POLICY_CANDIDATE.value,
                    content=content,
                    source_episode_ids=episode_ids,
                    source_fact_ids=[],
                    support_count=len(episode_ids),
                    distinct_session_count=len(sessions),
                    temporal_spread_days=0,
                    user_asserted_source_count=0,
                )
                saved += 1
            except Exception as exc:
                log.warning(
                    "policy_candidate_save_failed",
                    agent=row["agent"],
                    error=str(exc),
                )

        return saved

    def _config(self) -> dict:
        if self._settings is None:
            return {}
        dream = getattr(self._settings, "dream_config", None)
        if isinstance(dream, dict):
            return dream
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("dream", {})
        if isinstance(self._settings, dict):
            return self._settings.get("dream", {})
        return {}
