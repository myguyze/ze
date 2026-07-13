from __future__ import annotations

import asyncpg

from ze_logging import get_logger

log = get_logger(__name__)

_DEFAULT_KEEP_PER_THREAD = 3


class CheckpointPruner:
    """Trims LangGraph checkpoint history down to the most recent N per thread.

    LangGraph's AsyncPostgresSaver writes a full checkpoint on every node
    transition and never prunes old ones — resume/replay only ever reads the
    latest checkpoint per (thread_id, checkpoint_ns), so history beyond a
    small safety margin is pure storage growth. Runs against the main
    asyncpg pool since checkpoint_writes/checkpoint_blobs/checkpoints are
    plain tables in the same database as everything else.
    """

    def __init__(self, pool: asyncpg.Pool, keep_per_thread: int = _DEFAULT_KEEP_PER_THREAD) -> None:
        self._pool = pool
        self._keep = keep_per_thread

    async def run(self) -> None:
        async with self._pool.acquire() as conn:
            threads = await conn.fetch(
                "SELECT DISTINCT thread_id, checkpoint_ns FROM checkpoints"
            )

        totals = {"checkpoints": 0, "writes": 0, "blobs": 0}
        for row in threads:
            counts = await self._prune_thread(row["thread_id"], row["checkpoint_ns"])
            totals["checkpoints"] += counts["checkpoints"]
            totals["writes"] += counts["writes"]
            totals["blobs"] += counts["blobs"]

        if any(totals.values()):
            log.info("checkpoint_prune_done", threads=len(threads), **totals)

    async def _prune_thread(self, thread_id: str, checkpoint_ns: str) -> dict[str, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT checkpoint_id, checkpoint FROM checkpoints "
                "WHERE thread_id = $1 AND checkpoint_ns = $2 "
                "ORDER BY checkpoint_id DESC",
                thread_id,
                checkpoint_ns,
            )
            if len(rows) <= self._keep:
                return {"checkpoints": 0, "writes": 0, "blobs": 0}

            keep_rows, delete_rows = rows[: self._keep], rows[self._keep :]
            delete_ids = [r["checkpoint_id"] for r in delete_rows]

            referenced: set[tuple[str, str]] = set()
            for r in keep_rows:
                versions = (r["checkpoint"] or {}).get("channel_versions") or {}
                referenced.update((channel, str(version)) for channel, version in versions.items())

            async with conn.transaction():
                writes_result = await conn.execute(
                    "DELETE FROM checkpoint_writes "
                    "WHERE thread_id = $1 AND checkpoint_ns = $2 AND checkpoint_id = ANY($3::text[])",
                    thread_id,
                    checkpoint_ns,
                    delete_ids,
                )
                checkpoints_result = await conn.execute(
                    "DELETE FROM checkpoints "
                    "WHERE thread_id = $1 AND checkpoint_ns = $2 AND checkpoint_id = ANY($3::text[])",
                    thread_id,
                    checkpoint_ns,
                    delete_ids,
                )

                blob_rows = await conn.fetch(
                    "SELECT channel, version FROM checkpoint_blobs "
                    "WHERE thread_id = $1 AND checkpoint_ns = $2",
                    thread_id,
                    checkpoint_ns,
                )
                orphaned = [
                    (b["channel"], b["version"])
                    for b in blob_rows
                    if (b["channel"], b["version"]) not in referenced
                ]
                if orphaned:
                    await conn.executemany(
                        "DELETE FROM checkpoint_blobs "
                        "WHERE thread_id = $1 AND checkpoint_ns = $2 AND channel = $3 AND version = $4",
                        [(thread_id, checkpoint_ns, channel, version) for channel, version in orphaned],
                    )

            return {
                "checkpoints": _rowcount(checkpoints_result),
                "writes": _rowcount(writes_result),
                "blobs": len(orphaned),
            }


def _rowcount(result: str) -> int:
    # asyncpg execute() returns e.g. "DELETE 12"
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
