from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ze_core.logging import get_logger
from ze_core.telemetry.types import CostRecord

log = get_logger(__name__)


class SQLiteCostStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = None

    async def setup(self) -> None:
        try:
            import aiosqlite  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "aiosqlite is required by SQLiteCostStore."
                " Install it with: pip install ze-core[sqlite]"
            ) from exc
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_cost_log (
                id                TEXT PRIMARY KEY,
                session_id        TEXT,
                agent             TEXT NOT NULL DEFAULT 'unknown',
                flow_type         TEXT NOT NULL DEFAULT 'unknown',
                model             TEXT NOT NULL,
                prompt_tokens     INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens      INTEGER NOT NULL DEFAULT 0,
                cost_usd          REAL,
                duration_ms       INTEGER NOT NULL DEFAULT 0,
                generation_id     TEXT,
                audio_seconds     REAL,
                created_at        TEXT NOT NULL
            )
            """
        )
        await self._conn.commit()

    async def write(self, rec: CostRecord) -> None:
        if self._conn is None:
            log.warning("cost_write_skipped_no_connection")
            return
        try:
            await self._conn.execute(
                """
                INSERT INTO llm_cost_log
                    (id, session_id, agent, flow_type, model,
                     prompt_tokens, completion_tokens, total_tokens,
                     cost_usd, duration_ms, generation_id, audio_seconds, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    rec.session_id,
                    rec.agent,
                    rec.flow_type,
                    rec.model,
                    rec.prompt_tokens,
                    rec.completion_tokens,
                    rec.total_tokens,
                    rec.cost_usd,
                    rec.duration_ms,
                    rec.generation_id,
                    rec.audio_seconds,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await self._conn.commit()
        except Exception as exc:
            log.warning("cost_write_failed", error=str(exc))

    async def aclose(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
