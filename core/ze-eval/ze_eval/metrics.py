"""
Session-level token and latency metrics from llm_cost_log.

Ze's cost tracker writes a row to llm_cost_log for every LLM call, tagged
with the eval session_id. This module queries those rows after each scenario
to surface prompt/completion tokens and LLM-side duration.

Note: cost_usd is backfilled asynchronously by CostReconciler (runs every
15 min). Token counts and duration are available immediately.
"""

from __future__ import annotations

import os

import asyncpg

from ze_eval.types import SessionMetrics

_QUERY = """
SELECT
    COALESCE(SUM(prompt_tokens), 0)::int     AS prompt_tokens,
    COALESCE(SUM(completion_tokens), 0)::int AS completion_tokens,
    COALESCE(SUM(total_tokens), 0)::int      AS total_tokens,
    COALESCE(SUM(duration_ms), 0)::int       AS llm_duration_ms,
    COUNT(*)::int                            AS llm_calls,
    ARRAY_AGG(DISTINCT model)                AS models
FROM llm_cost_log
WHERE session_id = $1
"""


async def fetch_session_metrics(
    session_id: str,
    db_url: str | None = None,
) -> SessionMetrics | None:
    """
    Fetch token and duration metrics for one eval session.

    session_id should be the raw value passed to /eval/chat. The stored
    session_id in llm_cost_log is prefixed with "eval-" by the server;
    this function handles that prefix automatically.
    """
    url = db_url or os.environ.get(
        "DATABASE_URL", "postgresql://ze:ze@localhost:5432/ze"
    )
    stored_session_id = f"eval-{session_id}"

    try:
        conn = await asyncpg.connect(url)
    except Exception:
        return None

    try:
        row = await conn.fetchrow(_QUERY, stored_session_id)
        if row is None or row["llm_calls"] == 0:
            return None
        return SessionMetrics(
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            llm_duration_ms=row["llm_duration_ms"],
            llm_calls=row["llm_calls"],
            models=[m for m in (row["models"] or []) if m],
        )
    except Exception:
        return None
    finally:
        await conn.close()
