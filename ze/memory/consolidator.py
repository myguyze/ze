from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import UUID

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

from ze.logging import get_logger
from ze.memory.types import ConsolidationReport
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.telemetry.context import set_agent_context, set_flow_context

_MERGE_PROMPT = """\
You are merging two user facts that are semantically similar.
Fact A: {key_a} = {value_a}
Fact B: {key_b} = {value_b}
Return a single merged fact as JSON with exactly two keys: "key" and "value".
Use the more informative key. Keep the value concise and factual."""

_ARCHIVE_SYSTEM = (
    "Summarise the following AI assistant interactions into a single concise paragraph "
    "capturing the key facts, decisions, and outcomes. Be factual and brief."
)

_PROFILE_SYSTEM = """\
You are maintaining a structured profile of a single user based on their
interaction history with a personal AI assistant. Your output must be a JSON
object with exactly five string keys: "preferences", "habits", "topics",
"relationships", "goals". Each value should be a concise paragraph (2-4 sentences)
or an empty string if there is insufficient evidence. Do not invent information.
Base your response only on the provided facts and episode summaries."""

_PROFILE_MAX_SECTION = 400

_DEFAULTS = {
    "merge_silent_threshold": 0.95,
    "merge_llm_threshold": 0.85,
    "contradicted_ttl_days": 30,
    "unreviewed_ttl_days": 90,
    "expiry_grace_days": 7,
    "episode_recency_days": 14,
    "episode_archive_batch": 20,
    "episode_min_archive_batch": 10,
}


def _vec(embedding: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in embedding.tolist()) + "]"


class MemoryConsolidator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings
        self._log = get_logger(__name__)

    # ── Public ────────────────────────────────────────────────────────────────

    async def run(self) -> ConsolidationReport:
        set_flow_context("memory_consolidation")
        set_agent_context("memory_consolidation")
        start = time.monotonic()
        self._log.info("consolidation_start")

        merged = await self.dedup_facts()
        soft_expired, hard_deleted = await self.expire_facts()
        archived, deleted = await self.archive_episodes()
        profile_updated = await self.synthesise_profile()

        report = ConsolidationReport(
            facts_merged=merged,
            facts_soft_expired=soft_expired,
            facts_hard_deleted=hard_deleted,
            episodes_archived=archived,
            episodes_deleted=deleted,
            profile_updated=profile_updated,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        self._log.info("consolidation_done", **{
            k: v for k, v in report.__dict__.items()
        })
        return report

    async def synthesise_profile(self) -> bool:
        profile_cfg = self._settings.profile_config
        min_facts = int(profile_cfg.get("min_facts", 3))
        episode_limit = int(profile_cfg.get("episode_limit", 50))
        model = self._settings.config.get("models", {}).get("profile", "anthropic/claude-haiku-4-5")

        async with self._pool.acquire() as conn:
            fact_rows = await conn.fetch(
                "SELECT key, value FROM user_facts "
                "WHERE reviewed = true AND contradicted = false "
                "ORDER BY updated_at DESC"
            )
            episode_rows = await conn.fetch(
                "SELECT summary, response FROM episodes "
                "ORDER BY created_at DESC LIMIT $1",
                episode_limit,
            )
            profile_row = await conn.fetchrow(
                "SELECT preferences, habits, topics, relationships, goals, version "
                "FROM user_profile WHERE id = 1"
            )

        if len(fact_rows) < min_facts and not episode_rows:
            self._log.info("profile_synthesis_skipped", facts=len(fact_rows), episodes=len(episode_rows))
            return False

        current = {}
        if profile_row:
            current = {
                "preferences": profile_row["preferences"],
                "habits": profile_row["habits"],
                "topics": profile_row["topics"],
                "relationships": profile_row["relationships"],
                "goals": profile_row["goals"],
            }
        current_version = profile_row["version"] if profile_row else 0

        facts_block = "\n".join(f"- {r['key']}: {r['value']}" for r in fact_rows)
        episodes_block = "\n".join(
            f"- {r['summary'] or r['response'][:200]}" for r in episode_rows
        )

        user_prompt = (
            f"Current profile (update rather than replace where possible):\n"
            f"{json.dumps(current)}\n\n"
            f"Reviewed user facts:\n{facts_block}\n\n"
            f"Recent interaction summaries (newest first):\n{episodes_block}\n\n"
            f"Produce the updated profile JSON."
        )

        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": user_prompt}],
                model=model,
                system=_PROFILE_SYSTEM,
                max_tokens=600,
            )
            parsed = json.loads(raw)
        except Exception as exc:
            self._log.warning("profile_synthesis_failed", error=str(exc))
            return False

        required = {"preferences", "habits", "topics", "relationships", "goals"}
        if not required.issubset(parsed.keys()):
            self._log.warning("profile_synthesis_bad_json", keys=list(parsed.keys()))
            return False

        sections = {k: str(parsed[k])[:_PROFILE_MAX_SECTION] for k in required}

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE user_profile
                SET preferences = $1, habits = $2, topics = $3,
                    relationships = $4, goals = $5,
                    updated_at = NOW(), version = $6
                WHERE id = 1
                """,
                sections["preferences"],
                sections["habits"],
                sections["topics"],
                sections["relationships"],
                sections["goals"],
                current_version + 1,
            )

        self._log.info("profile_synthesis_done", version=current_version + 1)
        return True

    async def dedup_facts(self) -> int:
        cfg = self._cfg()
        silent_threshold = float(cfg["merge_silent_threshold"])
        llm_threshold = float(cfg["merge_llm_threshold"])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, key, value, agent, confidence, reviewed, updated_at, embedding
                FROM user_facts
                WHERE contradicted = false
                  AND expires_at IS NULL
                  AND embedding IS NOT NULL
                ORDER BY updated_at DESC
                """
            )

        if len(rows) < 2:
            return 0

        facts = list(rows)
        embeddings = [np.array(json.loads(r["embedding"])) for r in facts]
        merged_ids: set[UUID] = set()
        pairs_resolved = 0

        for i in range(len(facts)):
            if facts[i]["id"] in merged_ids:
                continue
            for j in range(i + 1, len(facts)):
                if facts[j]["id"] in merged_ids:
                    continue

                similarity = float(np.dot(embeddings[i], embeddings[j]))

                if similarity < llm_threshold:
                    continue

                fact_a, fact_b = facts[i], facts[j]

                # Never auto-merge reviewed facts
                if fact_a["reviewed"] or fact_b["reviewed"]:
                    continue

                # Keep newest; fact list is ordered DESC so index i is newer
                older_id = fact_b["id"]

                if similarity >= silent_threshold:
                    await self._mark_contradicted(older_id)
                    merged_ids.add(older_id)
                    pairs_resolved += 1
                    self._log.info(
                        "fact_dedup_silent",
                        kept=fact_a["key"],
                        removed=fact_b["key"],
                        similarity=round(similarity, 3),
                    )
                else:
                    merged = await self._llm_merge(fact_a, fact_b)
                    if merged:
                        await self._insert_merged_fact(merged, fact_a["agent"])
                        await self._mark_contradicted(fact_a["id"])
                        await self._mark_contradicted(fact_b["id"])
                        merged_ids.add(fact_a["id"])
                        merged_ids.add(fact_b["id"])
                        pairs_resolved += 1
                        self._log.info(
                            "fact_dedup_llm",
                            key_a=fact_a["key"],
                            key_b=fact_b["key"],
                            merged_key=merged["key"],
                            similarity=round(similarity, 3),
                        )
                    else:
                        # LLM failed — fall back to silent merge
                        await self._mark_contradicted(older_id)
                        merged_ids.add(older_id)
                        pairs_resolved += 1
                        self._log.warning(
                            "fact_dedup_llm_fallback",
                            kept=fact_a["key"],
                            removed=fact_b["key"],
                        )

                break  # one merge per fact per pass

        return pairs_resolved

    async def expire_facts(self) -> tuple[int, int]:
        cfg = self._cfg()
        contradicted_ttl = int(cfg["contradicted_ttl_days"])
        unreviewed_ttl = int(cfg["unreviewed_ttl_days"])
        grace_days = int(cfg["expiry_grace_days"])

        async with self._pool.acquire() as conn:
            # 1. Hard-delete facts whose grace period has elapsed
            grace_result = await conn.execute(
                "DELETE FROM user_facts WHERE expires_at IS NOT NULL AND expires_at < NOW()"
            )

            # 2. Hard-delete old contradicted facts
            contradicted_result = await conn.execute(
                f"DELETE FROM user_facts WHERE contradicted = true "
                f"AND updated_at < NOW() - INTERVAL '{contradicted_ttl} days'"
            )

            # 3. Soft-expire old unreviewed facts
            soft_result = await conn.execute(
                f"UPDATE user_facts "
                f"SET expires_at = NOW() + INTERVAL '{grace_days} days' "
                f"WHERE reviewed = false "
                f"AND updated_at < NOW() - INTERVAL '{unreviewed_ttl} days' "
                f"AND expires_at IS NULL"
            )

        hard_deleted = _parse_count(grace_result) + _parse_count(contradicted_result)
        soft_expired = _parse_count(soft_result)

        return soft_expired, hard_deleted

    async def archive_episodes(self) -> tuple[int, int]:
        cfg = self._cfg()
        recency_days = int(cfg["episode_recency_days"])
        batch_size = int(cfg["episode_archive_batch"])
        min_batch = int(cfg["episode_min_archive_batch"])

        batches_created = 0
        raws_deleted = 0

        while True:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT id, agent, prompt, response, summary, embedding, created_at
                    FROM episodes
                    WHERE is_archive = false
                      AND created_at < NOW() - INTERVAL '{recency_days} days'
                    ORDER BY created_at ASC
                    LIMIT {batch_size}
                    """
                )

            if len(rows) < min_batch:
                break

            batch_ids = [r["id"] for r in rows]
            start_dt: datetime = rows[0]["created_at"]
            end_dt: datetime = rows[-1]["created_at"]

            summary = await self._archive_summary(rows)
            if summary is None:
                self._log.warning("archive_batch_skipped", count=len(rows))
                break

            mean_embedding = _mean_embedding(
                [np.array(json.loads(r["embedding"])) for r in rows if r["embedding"]]
            )

            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO episodes (agent, prompt, response, summary, embedding, is_archive)
                        VALUES ($1, $2, $3, $4, $5::vector, true)
                        """,
                        "__archive__",
                        f"Archive of {len(rows)} episodes "
                        f"({_fmt_date(start_dt)} to {_fmt_date(end_dt)})",
                        summary,
                        summary,
                        _vec(mean_embedding),
                    )
                    await conn.execute(
                        "DELETE FROM episodes WHERE id = ANY($1::uuid[])",
                        batch_ids,
                    )

            batches_created += 1
            raws_deleted += len(rows)
            self._log.info(
                "episode_batch_archived",
                count=len(rows),
                from_date=_fmt_date(start_dt),
                to_date=_fmt_date(end_dt),
            )

        return batches_created, raws_deleted

    # ── Private ───────────────────────────────────────────────────────────────

    def _cfg(self) -> dict:
        cfg = self._settings.consolidation_config
        return {k: cfg.get(k, v) for k, v in _DEFAULTS.items()}

    def _haiku_model(self) -> str:
        return self._settings.config.get("models", {}).get(
            "synthesis", "anthropic/claude-haiku-4-5"
        )

    async def _mark_contradicted(self, fact_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_facts SET contradicted = true WHERE id = $1", fact_id
            )

    async def _insert_merged_fact(self, merged: dict, agent: str) -> None:
        value_embedding = self._embedder.encode(
            merged["value"], normalize_embeddings=True
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_facts (key, value, agent, confidence, embedding)
                VALUES ($1, $2, $3, 1.0, $4::vector)
                """,
                merged["key"],
                merged["value"],
                agent,
                _vec(value_embedding),
            )

    async def _llm_merge(self, fact_a, fact_b) -> dict | None:
        prompt = _MERGE_PROMPT.format(
            key_a=fact_a["key"], value_a=fact_a["value"],
            key_b=fact_b["key"], value_b=fact_b["value"],
        )
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._haiku_model(),
                max_tokens=100,
            )
            result = json.loads(raw)
            if "key" in result and "value" in result:
                return result
            self._log.warning("fact_merge_bad_json", raw=raw[:200])
            return None
        except Exception as exc:
            self._log.warning("fact_merge_failed", error=str(exc))
            return None

    async def _archive_summary(self, rows) -> str | None:
        parts = []
        for r in rows:
            text = r["summary"] or r["response"][:200]
            parts.append(f"- {text}")
        content = "\n".join(parts)
        try:
            return await self._client.complete(
                messages=[{"role": "user", "content": content}],
                model=self._haiku_model(),
                system=_ARCHIVE_SYSTEM,
                max_tokens=300,
            )
        except Exception as exc:
            self._log.warning("archive_summary_failed", error=str(exc))
            return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_count(result: str) -> int:
    # asyncpg returns e.g. "DELETE 3" or "UPDATE 5"
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError):
        return 0


def _mean_embedding(embeddings: list[np.ndarray]) -> np.ndarray:
    if not embeddings:
        return np.zeros(384)
    mean = np.mean(np.stack(embeddings), axis=0)
    norm = np.linalg.norm(mean)
    return mean / norm if norm > 0 else mean


def _fmt_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")
