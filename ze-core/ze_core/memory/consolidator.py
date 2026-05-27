from __future__ import annotations

import json
import time
from typing import Any

from ze_core.defaults import (
    MEMORY_CONTRADICTED_TTL_DAYS,
    MEMORY_EPISODE_ARCHIVE_BATCH,
    MEMORY_EPISODE_MIN_ARCHIVE_BATCH,
    MEMORY_EPISODE_RECENCY_DAYS,
    MEMORY_MERGE_LLM_THRESHOLD,
    MEMORY_MERGE_SILENT_THRESHOLD,
    MEMORY_UNREVIEWED_TTL_DAYS,
    MODEL_SYNTHESIS,
)
from ze_core.logging import get_logger
from ze_core.memory.postgres import _cosine_similarity, _parse_update_count, _to_list
from ze_core.memory.types import ConsolidationReport

log = get_logger(__name__)

_PROFILE_KEYS = {"preferences", "habits", "topics", "relationships", "goals"}


class MemoryConsolidator:
    def __init__(
        self,
        pool: Any,
        embedder: Any,
        openrouter_client: Any,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings

    async def run(self) -> ConsolidationReport:
        start = time.monotonic()
        report = ConsolidationReport()

        report.facts_merged = await self.dedup_facts()

        soft, hard = await self.expire_facts()
        report.facts_soft_expired = soft
        report.facts_hard_deleted = hard

        archived, deleted = await self.archive_episodes()
        report.episodes_archived = archived
        report.episodes_deleted = deleted

        report.profile_updated = await self.update_profile()
        report.duration_ms = int((time.monotonic() - start) * 1000)

        log.info(
            "memory_consolidation_complete",
            facts_merged=report.facts_merged,
            episodes_archived=report.episodes_archived,
            profile_updated=report.profile_updated,
            duration_ms=report.duration_ms,
        )
        return report

    async def dedup_facts(self) -> int:
        cfg = self._memory_config()
        silent_threshold = cfg.get("merge_silent_threshold", MEMORY_MERGE_SILENT_THRESHOLD)
        llm_threshold = cfg.get("merge_llm_threshold", MEMORY_MERGE_LLM_THRESHOLD)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, key, value, agent, confidence FROM user_facts"
                " WHERE contradicted = false ORDER BY updated_at DESC"
            )

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
                    async with self._pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE user_facts SET contradicted = true WHERE id = $1",
                            rows[drop]["id"],
                        )
                    merged += 1
                elif sim >= llm_threshold:
                    merged_value = await self._llm_merge(
                        rows[i]["value"], rows[j]["value"]
                    )
                    if merged_value:
                        new_emb = self._embedder.encode(merged_value)
                        emb_list = _to_list(new_emb)
                        async with self._pool.acquire() as conn:
                            await conn.execute(
                                "UPDATE user_facts SET contradicted = true WHERE id = $1",
                                rows[i]["id"],
                            )
                            await conn.execute(
                                "UPDATE user_facts SET contradicted = true WHERE id = $1",
                                rows[j]["id"],
                            )
                            await conn.execute(
                                "INSERT INTO user_facts"
                                " (key, value, agent, confidence, embedding)"
                                " VALUES ($1, $2, $3, $4, $5::vector)",
                                rows[i]["key"],
                                merged_value,
                                rows[i]["agent"],
                                max(rows[i]["confidence"], rows[j]["confidence"]),
                                emb_list,
                            )
                        contradicted_ids.add(rows[i]["id"])
                        contradicted_ids.add(rows[j]["id"])
                        merged += 1

        return merged

    async def expire_facts(self) -> tuple[int, int]:
        cfg = self._memory_config()
        unreviewed_ttl = cfg.get("unreviewed_ttl_days", MEMORY_UNREVIEWED_TTL_DAYS)
        contradicted_ttl = cfg.get("contradicted_ttl_days", MEMORY_CONTRADICTED_TTL_DAYS)

        async with self._pool.acquire() as conn:
            soft = await conn.execute(
                "UPDATE user_facts SET contradicted = true"
                " WHERE reviewed = false AND contradicted = false"
                " AND updated_at < NOW() - $1::interval",
                f"{unreviewed_ttl} days",
            )
            hard = await conn.execute(
                "DELETE FROM user_facts"
                " WHERE contradicted = true"
                " AND updated_at < NOW() - $1::interval",
                f"{contradicted_ttl} days",
            )

        return _parse_update_count(soft), _parse_update_count(hard)

    async def archive_episodes(self) -> tuple[int, int]:
        cfg = self._memory_config()
        recency_days = cfg.get("episode_recency_days", MEMORY_EPISODE_RECENCY_DAYS)
        min_batch = cfg.get("episode_min_archive_batch", MEMORY_EPISODE_MIN_ARCHIVE_BATCH)
        max_batch = cfg.get("episode_archive_batch", MEMORY_EPISODE_ARCHIVE_BATCH)

        async with self._pool.acquire() as conn:
            candidates = await conn.fetch(
                "SELECT id, prompt, response, summary FROM episodes"
                " WHERE is_archive = false"
                " AND created_at < NOW() - $1::interval"
                " ORDER BY created_at ASC LIMIT $2",
                f"{recency_days} days",
                max_batch,
            )

        if len(candidates) < min_batch:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM episodes WHERE is_archive = false"
                    " AND summary IS NOT NULL"
                    " AND created_at < NOW() - $1::interval",
                    f"{recency_days * 2} days",
                )
            return 0, _parse_update_count(result)

        parts = "\n\n".join(
            f"[{i + 1}] User: {r['prompt']}\nAssistant: {r['response']}"
            for i, r in enumerate(candidates)
        )
        try:
            archive_text = await self._client.complete(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Create a concise archival summary of these"
                            f" {len(candidates)} conversations:\n\n{parts}"
                        ),
                    }
                ],
                model=self._synthesis_model(),
            )
        except Exception as exc:
            log.warning("memory_archive_summarize_failed", error=str(exc))
            return 0, 0

        ids = [r["id"] for r in candidates]
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO episodes (agent, prompt, response, summary, is_archive)"
                " VALUES ('consolidator', 'archive', $1, $1, true)",
                archive_text,
            )
            await conn.execute(
                "DELETE FROM episodes WHERE id = ANY($1::uuid[])",
                ids,
            )

        return len(candidates), 0

    async def update_profile(self) -> bool:
        async with self._pool.acquire() as conn:
            facts_rows = await conn.fetch(
                "SELECT key, value FROM user_facts WHERE contradicted = false"
                " ORDER BY updated_at DESC LIMIT 100"
            )
            episode_rows = await conn.fetch(
                "SELECT summary FROM episodes WHERE summary IS NOT NULL"
                " ORDER BY created_at DESC LIMIT 20"
            )

        if not facts_rows and not episode_rows:
            return False

        facts_text = "\n".join(f"- {r['key']}: {r['value']}" for r in facts_rows)
        episodes_text = "\n".join(f"- {r['summary']}" for r in episode_rows)
        prompt = (
            "Based on these user facts and recent conversation summaries,"
            " synthesize a structured user profile.\n"
            "Respond with JSON containing exactly these keys:"
            " preferences, habits, topics, relationships, goals.\n\n"
            f"Facts:\n{facts_text}\n\nRecent conversations:\n{episodes_text}"
        )

        try:
            response = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._synthesis_model(),
            )
            profile_data = json.loads(response)
            if not _PROFILE_KEYS.issubset(profile_data.keys()):
                raise ValueError("missing required profile keys")
        except Exception as exc:
            log.warning("memory_update_profile_failed", error=str(exc))
            return False

        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_profile"
                " (id, preferences, habits, topics, relationships, goals, updated_at, version)"
                " VALUES (1, $1, $2, $3, $4, $5, NOW(), 1)"
                " ON CONFLICT (id) DO UPDATE SET"
                " preferences = $1, habits = $2, topics = $3,"
                " relationships = $4, goals = $5,"
                " updated_at = NOW(), version = user_profile.version + 1",
                profile_data["preferences"],
                profile_data["habits"],
                profile_data["topics"],
                profile_data["relationships"],
                profile_data["goals"],
            )
        return True

    # ── internal ──────────────────────────────────────────────────────────────

    async def _llm_merge(self, value_a: str, value_b: str) -> str | None:
        try:
            return await self._client.complete(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Merge these two similar facts into one concise fact:\n"
                            f"Fact 1: {value_a}\nFact 2: {value_b}\n"
                            "Return only the merged fact text, nothing else."
                        ),
                    }
                ],
                model=self._synthesis_model(),
            )
        except Exception as exc:
            log.warning("memory_llm_merge_failed", error=str(exc))
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

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
