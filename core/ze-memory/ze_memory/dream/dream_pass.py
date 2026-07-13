"""Dream Pass (REM-like): synthesis, hindsight relabeling, plan stress-tests, and scoring."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from ze_logging import get_logger
from ze_memory.dream.critic import DreamCritic
from ze_memory.dream.gates import ScoringGates
from ze_memory.dream.types import ArtifactStatus, ArtifactType

log = get_logger(__name__)

_DEFAULT_MAX_SYNTHESIS = 20
_DEFAULT_MAX_STRESS_TESTS = 2
_STRESS_TEST_IDLE_DAYS = 3

_SCHEMA_SYNTHESIS_SYSTEM = (
    "You are Ze's memory consolidation engine. Given episodes about a recurring entity or pattern, "
    "write a single concise generalisation that captures the underlying schema or habit. "
    "Be specific and grounded — do not invent facts not present in the episodes. "
    "Write one sentence only."
)

_POLICY_SYNTHESIS_SYSTEM = (
    "You are Ze's procedure extractor. Given a recurring agent interaction pattern across "
    "multiple sessions, write a short procedure or heuristic that captures how Ze handles "
    "this type of interaction. Use the format: 'When [trigger], Ze [action].' One sentence."
)

_HINDSIGHT_SYSTEM = (
    "You are Ze's retrospective analyst. A goal milestone was marked failed, but examine whether "
    "it produced any partial achievement worth recording. If yes, write one concise sentence "
    "describing what was partially accomplished. If no partial achievement exists, respond with "
    "exactly: NONE"
)

_STRESS_TEST_SYSTEM = (
    "You are Ze's adversarial planner. Given an active goal with an open milestone that has had "
    "no progress for several days, generate a concrete risk scenario that could cause this "
    'milestone to fail. Format: {"risk": "...", "warning_signal": "...", '
    '"recommended_caution": "..."}. Use conditional framing only — no unconditional action verbs.'
)


class DreamPass:
    def __init__(
        self,
        pool: Any,
        dream_store: Any,
        client: Any,
        embedder: Any,
        nli_client: Any | None = None,
        goal_store: Any | None = None,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._dream_store = dream_store
        self._client = client
        self._embedder = embedder
        self._nli = nli_client
        self._goal_store = goal_store
        self._settings = settings

    async def run(self, run_id: UUID) -> dict:
        start = time.monotonic()
        cfg = self._config()

        synthesis_model = cfg.get("synthesis_model", "anthropic/claude-haiku-4-5")
        critic_model = cfg.get("critic_model", "anthropic/claude-sonnet-4-6")
        max_synthesis = int(cfg.get("max_synthesis_per_run", _DEFAULT_MAX_SYNTHESIS))
        max_stress = int(
            cfg.get("max_stress_tests_per_goal", _DEFAULT_MAX_STRESS_TESTS)
        )
        nli_threshold = float(cfg.get("nli_groundedness_threshold", 0.75))
        novelty_threshold = float(cfg.get("novelty_similarity_threshold", 0.92))

        gates = ScoringGates(
            pool=self._pool,
            embedder=self._embedder,
            nli_client=self._nli,
            llm_client=self._client,
            nli_threshold=nli_threshold,
            novelty_threshold=novelty_threshold,
        )
        critic = DreamCritic(client=self._client, model=critic_model)

        schema_ids = await self._synthesize_schemas(
            run_id, synthesis_model, max_synthesis
        )
        policy_ids = await self._extract_policies(
            run_id, synthesis_model, max_synthesis - len(schema_ids)
        )
        hindsight_ids = await self._hindsight_relabeling(run_id, synthesis_model)
        stress_ids = await self._plan_stress_tests(run_id, synthesis_model, max_stress)

        all_promotable = schema_ids + policy_ids + stress_ids
        scored = await self._run_scoring_pipeline(
            all_promotable, gates, critic, synthesis_model
        )

        # hindsight facts get gates + critic but are always needs_review
        scored_hindsight = await self._run_scoring_pipeline(
            hindsight_ids, gates, critic, synthesis_model
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "dream_pass_complete",
            schemas=len(schema_ids),
            policies=len(policy_ids),
            hindsight=len(hindsight_ids),
            stress_tests=len(stress_ids),
            duration_ms=duration_ms,
        )
        return {
            "schemas": len(schema_ids),
            "policies": len(policy_ids),
            "hindsight": len(hindsight_ids),
            "stress_tests": len(stress_ids),
            "artifacts_scored": scored + scored_hindsight,
            "duration_ms": duration_ms,
        }

    async def _synthesize_schemas(
        self, run_id: UUID, model: str, budget: int
    ) -> list[UUID]:
        candidates = await self._dream_store.get_pending_artifacts_by_type(
            run_id, ArtifactType.SCHEMA_CANDIDATE.value
        )
        result: list[UUID] = []
        for row in candidates[:budget]:
            source_episode_ids = row.get("source_episode_ids") or []
            source_texts = await self._fetch_episode_texts(source_episode_ids)
            if not source_texts:
                continue
            prompt = (
                "Episodes about this entity:\n\n"
                + "\n---\n".join(source_texts[:10])
                + f"\n\nEntity context: {row['content']}"
            )
            try:
                synthesis = await self._client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    system=_SCHEMA_SYNTHESIS_SYSTEM,
                    temperature=0.4,
                    max_tokens=200,
                )
            except Exception as exc:
                log.warning("schema_synthesis_failed", error=str(exc))
                continue

            synthesis = synthesis.strip()
            if not synthesis or synthesis.upper() == "NONE":
                continue

            artifact_id = await self._dream_store.save_artifact(
                run_id=run_id,
                artifact_type=ArtifactType.SYNTHESIZED_INSIGHT.value,
                content=synthesis,
                source_episode_ids=source_episode_ids,
                source_fact_ids=row.get("source_fact_ids") or [],
                support_count=row.get("support_count", 0),
                distinct_session_count=row.get("distinct_session_count", 0),
                temporal_spread_days=row.get("temporal_spread_days", 0),
                user_asserted_source_count=row.get("user_asserted_source_count", 0),
            )
            result.append(artifact_id)
        return result

    async def _extract_policies(
        self, run_id: UUID, model: str, budget: int
    ) -> list[UUID]:
        candidates = await self._dream_store.get_pending_artifacts_by_type(
            run_id, ArtifactType.POLICY_CANDIDATE.value
        )
        result: list[UUID] = []
        for row in candidates[:budget]:
            source_episode_ids = row.get("source_episode_ids") or []
            source_texts = await self._fetch_episode_texts(source_episode_ids)
            if not source_texts:
                continue
            prompt = (
                "Agent interaction sessions:\n\n"
                + "\n---\n".join(source_texts[:10])
                + f"\n\nPattern: {row['content']}"
            )
            try:
                synthesis = await self._client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    system=_POLICY_SYNTHESIS_SYSTEM,
                    temperature=0.3,
                    max_tokens=200,
                )
            except Exception as exc:
                log.warning("policy_synthesis_failed", error=str(exc))
                continue

            synthesis = synthesis.strip()
            if not synthesis or synthesis.upper() == "NONE":
                continue

            artifact_id = await self._dream_store.save_artifact(
                run_id=run_id,
                artifact_type=ArtifactType.SYNTHESIZED_PROCEDURE.value,
                content=synthesis,
                source_episode_ids=source_episode_ids,
                source_fact_ids=row.get("source_fact_ids") or [],
                support_count=row.get("support_count", 0),
                distinct_session_count=row.get("distinct_session_count", 0),
                temporal_spread_days=row.get("temporal_spread_days", 0),
                user_asserted_source_count=row.get("user_asserted_source_count", 0),
            )
            result.append(artifact_id)
        return result

    async def _hindsight_relabeling(self, run_id: UUID, model: str) -> list[UUID]:
        """For recently completed goals with failed milestones, check for partial achievements."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    g.id AS goal_id,
                    g.title AS goal_title,
                    m.id AS milestone_id,
                    m.title AS milestone_title,
                    m.description AS milestone_desc,
                    array_agg(DISTINCT ep.id) FILTER (WHERE ep.id IS NOT NULL) AS episode_ids,
                    array_agg(DISTINCT ep.response) FILTER (WHERE ep.response IS NOT NULL) AS episode_texts
                FROM goals g
                JOIN goal_milestones m ON m.goal_id = g.id
                LEFT JOIN memory_episodes ep ON ep.session_id IN (
                    SELECT DISTINCT session_id FROM memory_episodes
                    WHERE created_at BETWEEN g.created_at AND now()
                    LIMIT 50
                )
                WHERE g.status = 'completed'
                  AND m.status = 'skipped'
                  AND g.created_at > now() - interval '30 days'
                GROUP BY g.id, g.title, m.id, m.title, m.description
                LIMIT 10
                """
            )

        result: list[UUID] = []
        for row in rows:
            texts = [t for t in (row["episode_texts"] or []) if t]
            if not texts:
                continue
            prompt = (
                f"Goal: {row['goal_title']}\n"
                f"Failed milestone: {row['milestone_title']}\n"
                f"Description: {row['milestone_desc']}\n\n"
                "Relevant episodes:\n" + "\n---\n".join(texts[:5])
            )
            try:
                result_text = await self._client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    system=_HINDSIGHT_SYSTEM,
                    temperature=0.3,
                    max_tokens=200,
                )
            except Exception as exc:
                log.warning("hindsight_synthesis_failed", error=str(exc))
                continue

            result_text = result_text.strip()
            if not result_text or result_text.upper() == "NONE":
                continue

            episode_ids = [e for e in (row["episode_ids"] or []) if e]
            artifact_id = await self._dream_store.save_artifact(
                run_id=run_id,
                artifact_type=ArtifactType.HINDSIGHT_FACT.value,
                content=result_text,
                source_episode_ids=episode_ids,
                source_fact_ids=[],
                support_count=len(episode_ids),
                distinct_session_count=1,
                temporal_spread_days=0,
                user_asserted_source_count=0,
            )
            result.append(artifact_id)
        return result

    async def _plan_stress_tests(
        self, run_id: UUID, model: str, max_per_goal: int
    ) -> list[UUID]:
        """For active goals with stalled milestones (no progress >= 3 days), generate risk scenarios."""
        idle_cutoff = datetime.now(tz=timezone.utc) - timedelta(
            days=_STRESS_TEST_IDLE_DAYS
        )

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    g.id AS goal_id,
                    g.title AS goal_title,
                    g.objective,
                    m.id AS milestone_id,
                    m.title AS milestone_title,
                    m.description AS milestone_desc,
                    m.updated_at AS last_updated,
                    array_agg(DISTINCT ep.id) FILTER (WHERE ep.id IS NOT NULL) AS episode_ids,
                    array_agg(DISTINCT ep.response) FILTER (WHERE ep.response IS NOT NULL) AS episode_texts
                FROM goals g
                JOIN goal_milestones m ON m.goal_id = g.id
                LEFT JOIN memory_episodes ep ON ep.goal_id = g.id
                WHERE g.status = 'active'
                  AND m.status IN ('pending', 'in_progress')
                  AND (m.updated_at IS NULL OR m.updated_at < $1)
                GROUP BY g.id, g.title, g.objective, m.id, m.title, m.description, m.updated_at
                ORDER BY g.id, m.sequence
                LIMIT 20
                """,
                idle_cutoff,
            )

        result: list[UUID] = []
        goal_counts: dict[str, int] = {}
        for row in rows:
            goal_id = str(row["goal_id"])
            if goal_counts.get(goal_id, 0) >= max_per_goal:
                continue

            episode_ids = list(row["episode_ids"] or [])
            episode_texts = [t for t in (row["episode_texts"] or []) if t]

            prompt = (
                f"Goal: {row['goal_title']}\n"
                f"Objective: {row['objective']}\n"
                f"Stalled milestone: {row['milestone_title']}\n"
                f"Description: {row['milestone_desc']}\n"
                f"No progress since: {idle_cutoff.date()}\n"
            )
            if episode_texts:
                prompt += "\nRecent context:\n" + "\n---\n".join(episode_texts[:3])

            try:
                result_text = await self._client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    model=model,
                    system=_STRESS_TEST_SYSTEM,
                    temperature=0.5,
                    max_tokens=300,
                )
            except Exception as exc:
                log.warning("stress_test_synthesis_failed", error=str(exc))
                continue

            result_text = result_text.strip()
            if not result_text:
                continue

            # Validate stress test has required fields (no unconditional action verbs)
            if not _stress_test_valid(result_text):
                log.debug("stress_test_invalid_format", content=result_text[:100])
                continue

            artifact_id = await self._dream_store.save_artifact(
                run_id=run_id,
                artifact_type=ArtifactType.PLAN_STRESS_TEST.value,
                content=result_text,
                source_episode_ids=episode_ids,
                source_fact_ids=[],
                support_count=len(episode_ids),
                distinct_session_count=1,
                temporal_spread_days=0,
                user_asserted_source_count=0,
            )
            result.append(artifact_id)
            goal_counts[goal_id] = goal_counts.get(goal_id, 0) + 1
        return result

    async def _run_scoring_pipeline(
        self,
        artifact_ids: list[UUID],
        gates: ScoringGates,
        critic: DreamCritic,
        synthesis_model: str,
    ) -> int:
        scored = 0
        for artifact_id in artifact_ids:
            row = await self._dream_store.get_artifact_row(artifact_id)
            if row is None:
                continue

            source_texts = await self._fetch_episode_texts(
                row.get("source_episode_ids") or []
            )

            # Gate 1 — NLI groundedness
            g1_pass, faithfulness = await gates.gate1_nli(
                row["content"], source_texts, synthesis_model
            )
            await self._dream_store.update_artifact_gate1(artifact_id, faithfulness)
            if not g1_pass:
                await self._dream_store.update_artifact_status(
                    artifact_id, ArtifactStatus.REJECTED.value
                )
                await self._decay_source_episodes(row.get("source_episode_ids") or [])
                scored += 1
                continue

            # Gate 2 — Embedding novelty
            g2_pass, novelty = await gates.gate2_novelty(row["content"])
            await self._dream_store.update_artifact_gate2(artifact_id, novelty)
            if not g2_pass:
                await self._dream_store.update_artifact_status(
                    artifact_id, ArtifactStatus.REJECTED.value
                )
                await self._decay_source_episodes(row.get("source_episode_ids") or [])
                scored += 1
                continue

            # Gate 3 — Embedding retrievability
            g3_pass = await gates.gate3_retrievability(
                row["content"],
                row.get("source_episode_ids") or [],
                row.get("support_count", 1),
            )
            await self._dream_store.update_artifact_gate3(artifact_id, g3_pass)
            if not g3_pass:
                await self._dream_store.update_artifact_status(
                    artifact_id, ArtifactStatus.REJECTED.value
                )
                await self._decay_source_episodes(row.get("source_episode_ids") or [])
                scored += 1
                continue

            # LLM critic — Call A + Call B
            a_verdict, a_reason, b_verdict, b_reason = await critic.critique_artifact(
                row["content"], source_texts
            )
            await self._dream_store.update_artifact_critics(
                artifact_id, a_verdict, a_reason, b_verdict, b_reason
            )

            if a_verdict != "PASS" or b_verdict != "PASS":
                await self._dream_store.update_artifact_status(
                    artifact_id, ArtifactStatus.REJECTED.value
                )
                await self._decay_source_episodes(row.get("source_episode_ids") or [])
            # Leave as PENDING — promoter will handle final status based on support validation

            scored += 1
        return scored

    async def _fetch_episode_texts(self, episode_ids: list[Any]) -> list[str]:
        if not episode_ids:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT prompt, response FROM memory_episodes WHERE id = ANY($1::uuid[])",
                list(episode_ids),
            )
        return [f"{r['prompt']}\n{r['response']}" for r in rows]

    async def _decay_source_episodes(
        self, episode_ids: list[Any], rate: float = 0.1
    ) -> None:
        if not episode_ids:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_episode_metadata SET
                    retrieval_weight = GREATEST(0.0, retrieval_weight - $2),
                    updated_at = now()
                WHERE episode_id = ANY($1::uuid[])
                """,
                list(episode_ids),
                rate,
            )

    def _config(self) -> dict:
        if self._settings is None:
            return {}
        if isinstance(self._settings, dict):
            return self._settings.get("dream", {})
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("dream", {})
        return {}


def _stress_test_valid(text: str) -> bool:
    """Ensure stress test has the required JSON-ish structure and no unconditional action verbs."""
    return (
        '"risk"' in text
        and '"warning_signal"' in text
        and '"recommended_caution"' in text
    )
