from __future__ import annotations

from typing import Any

from ze_logging import get_logger

from ze_memory.defaults import (
    MODEL_SYNTHESIS,
    SESSION_SUMMARY_ENABLED,
    SESSION_SUMMARY_MAX_SESSIONS_PER_RUN,
    SESSION_SUMMARY_MAX_TRANSCRIPT_TOKENS,
    SESSION_SUMMARY_MIN_EPISODES,
)

log = get_logger(__name__)

_DEFAULT_INACTIVITY_MINUTES = 30

_SUMMARY_SYSTEM = (
    "You are a memory consolidator for a personal AI assistant. "
    "Write a concise third-person narrative summary (≤200 words) of the following "
    "conversation session. Capture: main topics discussed, decisions made, outcomes "
    "reached, and any user intent or sentiment worth remembering in future sessions. "
    "Do not add information not present in the source. Use past tense."
)

_EXCLUDED_SESSION_IDS = ("", "app-main", "consolidator", "migrated")
_EXCLUDED_PREFIXES = ("workflow:", "onboarding:", "eval-")


def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def _is_excluded_session(session_id: str) -> bool:
    if session_id in _EXCLUDED_SESSION_IDS:
        return True
    return any(session_id.startswith(p) for p in _EXCLUDED_PREFIXES)


class SessionSummariser:
    job_id = "session_summary"

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

    async def run(self) -> int:
        """Find closed sessions without up-to-date summaries and generate them.

        Returns the number of sessions summarised.
        """
        cfg = self._config()
        if not cfg.get("enabled", SESSION_SUMMARY_ENABLED):
            return 0

        inactivity_minutes = self._inactivity_minutes()
        min_episodes = int(cfg.get("min_episodes", SESSION_SUMMARY_MIN_EPISODES))
        max_sessions = int(cfg.get("max_sessions_per_run", SESSION_SUMMARY_MAX_SESSIONS_PER_RUN))
        max_tokens = int(cfg.get("max_transcript_tokens", SESSION_SUMMARY_MAX_TRANSCRIPT_TOKENS))
        model = cfg.get("model", self._synthesis_model())

        candidates = await self._fetch_candidates(inactivity_minutes, min_episodes, max_sessions)
        summarised = 0

        for row in candidates:
            session_id = row["session_id"]
            try:
                episodes = await self._fetch_transcript(session_id)
                if len(episodes) < min_episodes:
                    continue

                transcript = self._build_transcript(episodes, max_tokens)
                summary = await self._generate_summary(session_id, transcript, model)
                if not summary:
                    continue

                embedding = self._embedder.encode(summary)
                await self._upsert(
                    session_id=session_id,
                    summary=summary,
                    episode_count=len(episodes),
                    last_turn_at=row["last_turn_at"],
                    embedding=embedding,
                )
                summarised += 1
                log.info("session_summary_written", session_id=session_id, episodes=len(episodes))
            except Exception as exc:
                log.warning("session_summary_failed", session_id=session_id, error=str(exc))

        if summarised:
            log.info("session_summary_job_complete", summarised=summarised)
        return summarised

    async def _fetch_candidates(
        self,
        inactivity_minutes: int,
        min_episodes: int,
        max_sessions: int,
    ) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT
                    e.session_id,
                    COUNT(*)                        AS episode_count,
                    MAX(e.created_at)               AS last_turn_at,
                    MAX(s.summary_updated_at)       AS existing_summary_at
                FROM memory_episodes e
                LEFT JOIN memory_session_summaries s ON s.session_id = e.session_id
                WHERE
                    e.summary IS NULL
                    AND e.session_id <> ALL($4::text[])
                    AND e.session_id NOT LIKE 'workflow:%'
                    AND e.session_id NOT LIKE 'onboarding:%'
                    AND e.session_id NOT LIKE 'eval-%'
                GROUP BY e.session_id
                HAVING
                    COUNT(*) >= $2
                    AND MAX(e.created_at) < now() - ($1 || ' minutes')::interval
                    AND (
                        MAX(s.summary_updated_at) IS NULL
                        OR MAX(e.created_at) > MAX(s.summary_updated_at)
                    )
                ORDER BY MAX(e.created_at) ASC
                LIMIT $3
                """,
                str(inactivity_minutes),
                min_episodes,
                max_sessions,
                list(_EXCLUDED_SESSION_IDS),
            )

    async def _fetch_transcript(self, session_id: str) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT agent, prompt, response, created_at
                FROM memory_episodes
                WHERE session_id = $1 AND summary IS NULL
                ORDER BY created_at ASC
                """,
                session_id,
            )

    def _build_transcript(self, episodes: list, max_tokens: int) -> str:
        """Build transcript text, dropping oldest turns first when over the token limit."""
        turns = [
            f"User: {ep['prompt']}\nZe: {ep['response']}"
            for ep in episodes
        ]
        while turns:
            text = "\n---\n".join(turns)
            if len(text) // 4 <= max_tokens:
                return text
            turns.pop(0)
        return ""

    async def _generate_summary(self, session_id: str, transcript: str, model: str) -> str | None:
        if not transcript:
            return None
        try:
            return await self._client.complete(
                messages=[
                    {"role": "system", "content": _SUMMARY_SYSTEM},
                    {"role": "user", "content": f"Session: {session_id}\n\n{transcript}"},
                ],
                model=model,
                max_tokens=400,
            )
        except Exception as exc:
            log.warning("session_summary_llm_failed", session_id=session_id, error=str(exc))
            return None

    async def _upsert(
        self,
        session_id: str,
        summary: str,
        episode_count: int,
        last_turn_at: Any,
        embedding: Any,
    ) -> None:
        emb_list = _to_list(embedding)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_session_summaries
                    (session_id, summary, episode_count, last_turn_at, summary_updated_at, embedding)
                VALUES ($1, $2, $3, $4, now(), $5::vector)
                ON CONFLICT (session_id) DO UPDATE SET
                    summary            = EXCLUDED.summary,
                    episode_count      = EXCLUDED.episode_count,
                    last_turn_at       = EXCLUDED.last_turn_at,
                    summary_updated_at = now(),
                    embedding          = EXCLUDED.embedding
                """,
                session_id,
                summary,
                episode_count,
                last_turn_at,
                emb_list,
            )

    def _config(self) -> dict:
        if self._settings is None:
            return {}
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("memory", {}).get("session_summary", {})
        if isinstance(self._settings, dict):
            return self._settings.get("memory", {}).get("session_summary", {})
        return {}

    def _inactivity_minutes(self) -> int:
        if self._settings is None:
            return _DEFAULT_INACTIVITY_MINUTES
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return int(cfg.get("session_inactivity_minutes", _DEFAULT_INACTIVITY_MINUTES))
        if isinstance(self._settings, dict):
            return int(self._settings.get("session_inactivity_minutes", _DEFAULT_INACTIVITY_MINUTES))
        return _DEFAULT_INACTIVITY_MINUTES

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
