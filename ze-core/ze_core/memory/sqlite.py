"""SQLite-backed MemoryStore using numpy cosine scan for vector similarity.

For development and low-volume personal use — no PostgreSQL or pgvector required.
Embeddings are stored as JSON arrays; similarity is computed in Python via numpy.

Usage::

    store = SQLiteMemoryStore("app.db", embedder, openrouter_client)
    await store.setup()   # creates schema, opens connection
    ...
    await store.aclose()
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ze_core.defaults import (
    MEMORY_CONTRADICTION_THRESHOLD,
    MEMORY_EPISODES_FETCH_LIMIT,
    MEMORY_EPISODES_TOKEN_BUDGET,
    MEMORY_FACTS_TOKEN_BUDGET,
    MODEL_SYNTHESIS,
)
from ze_core.logging import get_logger
from ze_core.memory.types import Episode, MemoryContext, UserFact, UserProfile

log = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_facts (
    id           TEXT PRIMARY KEY,
    key          TEXT NOT NULL,
    value        TEXT NOT NULL,
    agent        TEXT NOT NULL DEFAULT 'global',
    confidence   REAL NOT NULL DEFAULT 1.0,
    reviewed     INTEGER NOT NULL DEFAULT 0,
    contradicted INTEGER NOT NULL DEFAULT 0,
    embedding    TEXT,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (
    id         TEXT PRIMARY KEY,
    agent      TEXT NOT NULL,
    prompt     TEXT NOT NULL,
    response   TEXT NOT NULL,
    summary    TEXT,
    embedding  TEXT,
    is_archive INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    preferences   TEXT,
    habits        TEXT,
    topics        TEXT,
    relationships TEXT,
    goals         TEXT,
    updated_at    TEXT NOT NULL,
    version       INTEGER NOT NULL DEFAULT 1
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cosine(a: list[float], b: list[float]) -> float:
    import numpy as np
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    denom = float(np.linalg.norm(va)) * float(np.linalg.norm(vb))
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def _to_list(embedding: Any) -> list[float]:
    return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)


class SQLiteMemoryStore:
    """MemoryStore backed by SQLite + numpy cosine scan.

    Drop-in replacement for the Postgres ``MemoryStore`` for development and
    single-user deployments that don't need pgvector.
    """

    def __init__(
        self,
        db_path: str,
        embedder: Any,
        openrouter_client: Any,
        settings: Any = None,
    ) -> None:
        self._db_path = db_path
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings
        self._conn: Any = None

    async def setup(self) -> None:
        """Open the database connection and create the schema if it doesn't exist."""
        try:
            import aiosqlite
        except ImportError as exc:
            raise ImportError(
                "aiosqlite is required for SQLite storage. "
                "Install it with: pip install 'ze-core[sqlite]'"
            ) from exc
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        log.info("sqlite_store_ready", db=self._db_path)

    async def aclose(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ── public API ────────────────────────────────────────────────────────────

    async def get_context(
        self,
        prompt_embedding: Any,
        agent: str,
        token_budget: dict[str, int] | None = None,
    ) -> MemoryContext:
        budget = {
            "facts": MEMORY_FACTS_TOKEN_BUDGET,
            "episodes": MEMORY_EPISODES_TOKEN_BUDGET,
            **(token_budget or {}),
        }
        prompt_vec = _to_list(prompt_embedding)

        facts = await self._fetch_facts(agent, prompt_vec, budget["facts"])
        episodes = await self._fetch_episodes(prompt_vec, budget["episodes"])
        profile = await self.get_profile()

        token_est = sum(len(f.value) // 4 for f in facts) + sum(
            len(e.summary or e.response[:200]) // 4 for e in episodes
        )
        return MemoryContext(
            facts=facts,
            episodes=episodes,
            token_estimate=token_est,
            profile=profile,
        )

    async def write_episode(
        self,
        agent: str,
        prompt: str,
        response: str,
        embedding: Any,
    ) -> None:
        try:
            await self._conn.execute(
                "INSERT INTO episodes (id, agent, prompt, response, embedding, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), agent, prompt, response,
                 json.dumps(_to_list(embedding)), _now()),
            )
            await self._conn.commit()
        except Exception as exc:
            log.warning("sqlite_write_episode_failed", error=str(exc))

    async def propose_facts(self, proposals: list[UserFact]) -> None:
        for fact in proposals:
            try:
                await self._write_fact_with_contradiction_check(fact)
            except Exception as exc:
                log.warning("sqlite_propose_fact_failed", key=fact.key, error=str(exc))

    async def get_profile(self) -> UserProfile | None:
        async with self._conn.execute(
            "SELECT preferences, habits, topics, relationships, goals, updated_at, version"
            " FROM user_profile WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        if not any([row["preferences"], row["habits"], row["topics"],
                    row["relationships"], row["goals"]]):
            return None
        return UserProfile(
            preferences=row["preferences"] or "",
            habits=row["habits"] or "",
            topics=row["topics"] or "",
            relationships=row["relationships"] or "",
            goals=row["goals"] or "",
            updated_at=datetime.fromisoformat(row["updated_at"]),
            version=row["version"],
        )

    # ── private ───────────────────────────────────────────────────────────────

    async def _fetch_facts(
        self, agent: str, prompt_vec: list[float], budget: int
    ) -> list[UserFact]:
        async with self._conn.execute(
            "SELECT id, key, value, agent, confidence, reviewed, contradicted, embedding"
            " FROM user_facts"
            " WHERE contradicted = 0 AND (agent = ? OR agent = 'global')"
            " ORDER BY updated_at DESC",
            (agent,),
        ) as cur:
            rows = await cur.fetchall()

        # rank by cosine similarity; agent-specific rows get a small boost
        scored: list[tuple[float, Any]] = []
        for row in rows:
            if row["embedding"]:
                sim = _cosine(prompt_vec, json.loads(row["embedding"]))
                boost = 0.0 if row["agent"] == agent else -0.05
                scored.append((sim + boost, row))
            else:
                scored.append((0.0, row))
        scored.sort(key=lambda x: x[0], reverse=True)

        facts: list[UserFact] = []
        used = 0
        for _, row in scored:
            cost = len(row["value"]) // 4
            if used + cost > budget:
                break
            facts.append(UserFact(
                key=row["key"],
                value=row["value"],
                agent=row["agent"],
                confidence=row["confidence"],
                reviewed=bool(row["reviewed"]),
                contradicted=bool(row["contradicted"]),
                id=uuid.UUID(row["id"]),
            ))
            used += cost
        return facts

    async def _fetch_episodes(
        self, prompt_vec: list[float], budget: int
    ) -> list[Episode]:
        async with self._conn.execute(
            "SELECT id, agent, prompt, response, summary, embedding, is_archive, created_at"
            " FROM episodes WHERE embedding IS NOT NULL"
        ) as cur:
            rows = await cur.fetchall()

        scored: list[tuple[float, Any]] = []
        for row in rows:
            sim = _cosine(prompt_vec, json.loads(row["embedding"]))
            scored.append((sim, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:MEMORY_EPISODES_FETCH_LIMIT]

        episodes: list[Episode] = []
        used = 0
        for _, row in scored:
            text = row["summary"] or row["response"][:200]
            cost = len(text) // 4
            if used + cost > budget:
                break
            episodes.append(Episode(
                agent=row["agent"],
                prompt=row["prompt"],
                response=row["response"],
                summary=row["summary"],
                is_archive=bool(row["is_archive"]),
                id=uuid.UUID(row["id"]),
            ))
            used += cost
        return episodes

    async def _write_fact_with_contradiction_check(self, fact: UserFact) -> None:
        threshold = MEMORY_CONTRADICTION_THRESHOLD
        if self._settings:
            cfg = getattr(self._settings, "config", {}) or {}
            threshold = cfg.get("memory", {}).get("contradiction_threshold", threshold)

        value_emb = _to_list(self._embedder.encode(fact.value))

        async with self._conn.execute(
            "SELECT id FROM user_facts WHERE key = ? AND contradicted = 0",
            (fact.key,),
        ) as cur:
            exact = await cur.fetchall()
        for row in exact:
            await self._conn.execute(
                "UPDATE user_facts SET contradicted = 1 WHERE id = ?", (row["id"],)
            )

        async with self._conn.execute(
            "SELECT id, value FROM user_facts WHERE contradicted = 0 AND key != ?",
            (fact.key,),
        ) as cur:
            others = await cur.fetchall()
        for row in others:
            other_emb = _to_list(self._embedder.encode(row["value"]))
            if _cosine(value_emb, other_emb) > threshold:
                await self._conn.execute(
                    "UPDATE user_facts SET contradicted = 1 WHERE id = ?", (row["id"],)
                )

        await self._conn.execute(
            "INSERT INTO user_facts"
            " (id, key, value, agent, confidence, reviewed, contradicted, embedding, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()), fact.key, fact.value, fact.agent,
                fact.confidence, int(fact.reviewed), int(fact.contradicted),
                json.dumps(value_emb), _now(),
            ),
        )
        await self._conn.commit()

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
