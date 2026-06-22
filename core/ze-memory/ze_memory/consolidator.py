from __future__ import annotations

import time
from typing import Any

from ze_logging import get_logger

from ze_memory.defaults import (
    CONTRADICTED_TTL_DAYS,
    EPISODE_ARCHIVE_DAYS,
    EPISODE_ARCHIVE_BATCH,
    EPISODE_MIN_ARCHIVE_BATCH,
    EXPIRY_GRACE_DAYS,
    MAX_SESSIONS_PER_RUN,
    MERGE_LLM_THRESHOLD,
    MERGE_SILENT_THRESHOLD,
    MIN_SESSION_EPISODES,
    MODEL_SYNTHESIS,
    SESSION_GROUPING_ENABLED,
    UNREVIEWED_TTL_DAYS,
)
from ze_memory.consolidation_store import PostgresConsolidationStore, _cosine_similarity
from ze_memory.synthesizer import ProfileSynthesizer
from ze_memory.types import ConsolidationReport

log = get_logger(__name__)


class MemoryConsolidator:
    def __init__(
        self,
        store: PostgresConsolidationStore,
        embedder: Any,
        openrouter_client: Any,
        settings: Any = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings
        self._synthesizer = ProfileSynthesizer(
            store=store,
            openrouter_client=openrouter_client,
            settings=settings,
        )

    async def run(self) -> ConsolidationReport:
        start = time.monotonic()
        report = ConsolidationReport()

        report.facts_merged = await self.dedup_facts()

        soft, hard = await self.expire_facts()
        report.facts_soft_expired = soft
        report.facts_hard_deleted = hard

        report.session_episodes_archived = await self.archive_session_episodes()

        archived, deleted = await self.archive_episodes()
        report.episodes_archived = archived
        report.episodes_deleted = deleted

        report.profile_updated = await self._synthesizer.update_profile()
        report.duration_ms = int((time.monotonic() - start) * 1000)

        log.info(
            "memory_consolidation_complete",
            facts_merged=report.facts_merged,
            session_episodes_archived=report.session_episodes_archived,
            episodes_archived=report.episodes_archived,
            profile_updated=report.profile_updated,
            duration_ms=report.duration_ms,
        )
        return report

    async def dedup_facts(self) -> int:
        cfg = self._memory_config()
        silent_threshold = cfg.get("merge_silent_threshold", MERGE_SILENT_THRESHOLD)
        llm_threshold = cfg.get("merge_llm_threshold", MERGE_LLM_THRESHOLD)

        rows = await self._store.fetch_active_facts()
        if len(rows) < 2:
            return 0

        embeddings = [self._embedder.encode(row["value"]) for row in rows]
        contradicted_ids: set = set()
        merged = 0

        for i in range(len(rows)):
            if rows[i]["id"] in contradicted_ids:
                continue
            for j in range(i + 1, len(rows)):
                if rows[j]["id"] in contradicted_ids:
                    continue
                sim = _cosine_similarity(embeddings[i], embeddings[j])
                if sim >= silent_threshold:
                    keep, drop = (
                        (i, j)
                        if rows[i]["confidence"] >= rows[j]["confidence"]
                        else (j, i)
                    )
                    contradicted_ids.add(rows[drop]["id"])
                    await self._store.mark_contradicted(rows[drop]["id"])
                    merged += 1
                elif sim >= llm_threshold:
                    merged_value = await self._llm_merge(rows[i]["value"], rows[j]["value"])
                    if merged_value:
                        new_emb = self._embedder.encode(merged_value)
                        await self._store.mark_contradicted(rows[i]["id"])
                        await self._store.mark_contradicted(rows[j]["id"])
                        await self._store.insert_merged_fact(
                            rows[i]["predicate"],
                            merged_value,
                            max(rows[i]["confidence"], rows[j]["confidence"]),
                            new_emb,
                        )
                        contradicted_ids.add(rows[i]["id"])
                        contradicted_ids.add(rows[j]["id"])
                        merged += 1

        return merged

    async def expire_facts(self) -> tuple[int, int]:
        cfg = self._memory_config()
        unreviewed_ttl = cfg.get("unreviewed_ttl_days", UNREVIEWED_TTL_DAYS)
        grace_days = cfg.get("expiry_grace_days", EXPIRY_GRACE_DAYS)
        contradicted_ttl = cfg.get("contradicted_ttl_days", CONTRADICTED_TTL_DAYS)
        hard = await self._store.delete_expired_facts()
        hard += await self._store.delete_contradicted_facts(contradicted_ttl)
        soft = await self._store.soft_expire_unreviewed_facts(unreviewed_ttl, grace_days)
        return soft, hard

    async def archive_episodes(self) -> tuple[int, int]:
        cfg = self._consolidation_config()
        recency_days = cfg.get(
            "episode_archive_days",
            cfg.get("episode_recency_days", EPISODE_ARCHIVE_DAYS),
        )
        min_batch = cfg.get("episode_min_archive_batch", EPISODE_MIN_ARCHIVE_BATCH)
        max_batch = cfg.get("episode_archive_batch", EPISODE_ARCHIVE_BATCH)

        candidates = await self._store.fetch_episode_candidates(recency_days, max_batch)

        if len(candidates) < min_batch:
            deleted = await self._store.delete_old_episode_summaries(recency_days)
            return 0, deleted

        parts = "\n\n".join(
            f"[{i + 1}] User: {r['prompt']}\nAssistant: {r['response']}"
            for i, r in enumerate(candidates)
        )
        try:
            archive_text = await self._client.complete(
                messages=[{
                    "role": "user",
                    "content": (
                        f"Create a concise archival summary of these"
                        f" {len(candidates)} conversations:\n\n{parts}"
                    ),
                }],
                model=self._synthesis_model(),
            )
        except Exception as exc:
            log.warning("memory_archive_summarize_failed", error=str(exc))
            return 0, 0

        await self._store.insert_archive_episode(archive_text)
        await self._store.delete_episodes_by_ids([r["id"] for r in candidates])
        return len(candidates), 0

    async def archive_session_episodes(self) -> int:
        cfg = self._consolidation_config()
        enabled = cfg.get("session_grouping_enabled", SESSION_GROUPING_ENABLED)
        if not enabled:
            return 0

        recency_days = cfg.get(
            "episode_archive_days",
            cfg.get("episode_recency_days", EPISODE_ARCHIVE_DAYS),
        )
        min_session_episodes = cfg.get("min_session_episodes", MIN_SESSION_EPISODES)
        max_sessions = cfg.get("max_sessions_per_run", MAX_SESSIONS_PER_RUN)

        sessions = await self._store.fetch_session_archive_candidates(
            recency_days,
            min_session_episodes,
            max_sessions,
        )
        archived = 0

        for session in sessions:
            session_id = session["session_id"]

            if await self._store.session_has_eager_summary(session_id):
                deleted = await self._store.delete_raw_session_episodes(session_id, recency_days)
                if deleted:
                    archived += 1
                    log.info(
                        "memory_session_eager_summary_reused",
                        session_id=session_id,
                        deleted=deleted,
                    )
                continue

            episodes = await self._store.fetch_raw_session_episodes(session_id, recency_days)
            if len(episodes) < min_session_episodes:
                continue

            summary = await self._summarize_session(session_id, episodes)
            if not summary:
                continue

            try:
                embedding = self._embedder.encode(summary)
                deleted = await self._store.replace_session_episodes_with_summary(
                    session_id=session_id,
                    episode_count=len(episodes),
                    summary=summary,
                    embedding=embedding,
                    recency_days=recency_days,
                )
            except Exception as exc:
                log.warning(
                    "memory_session_archive_replace_failed",
                    session_id=session_id,
                    error=str(exc),
                )
                continue

            if deleted:
                archived += 1

        return archived

    async def update_profile(self) -> bool:
        return await self._synthesizer.update_profile()

    async def _llm_merge(self, value_a: str, value_b: str) -> str | None:
        try:
            return await self._client.complete(
                messages=[{
                    "role": "user",
                    "content": (
                        f"Merge these two similar facts into one concise fact:\n"
                        f"Fact 1: {value_a}\nFact 2: {value_b}\n"
                        "Return only the merged fact text, nothing else."
                    ),
                }],
                model=self._synthesis_model(),
            )
        except Exception as exc:
            log.warning("memory_llm_merge_failed", error=str(exc))
            return None

    async def _summarize_session(self, session_id: str, episodes: list) -> str | None:
        parts = "\n".join(
            f"User: {episode['prompt']}\nZe: {episode['response']}"
            for episode in episodes
        )
        try:
            return await self._client.complete(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a memory consolidator. Summarise this conversation "
                            "session into a concise third-person narrative (<=250 words). "
                            "Capture main topics, decisions, outcomes, and any user intent "
                            "or sentiment that may be relevant in future sessions. Do not "
                            "fabricate anything not present in the source."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Session {session_id} contains {len(episodes)} episodes:\n\n"
                            f"{parts}"
                        ),
                    },
                ],
                model=self._synthesis_model(),
            )
        except Exception as exc:
            log.warning(
                "memory_session_archive_summarize_failed",
                session_id=session_id,
                error=str(exc),
            )
            return None

    def _memory_config(self) -> dict:
        if self._settings is None:
            return {}
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("memory", {})
        if isinstance(self._settings, dict):
            return self._settings.get("memory", {})
        return {}

    def _consolidation_config(self) -> dict:
        memory_cfg = self._memory_config()
        cfg = dict(memory_cfg)
        consolidation_cfg = memory_cfg.get("consolidation", {})
        if isinstance(consolidation_cfg, dict):
            cfg.update(consolidation_cfg)
        return cfg

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
