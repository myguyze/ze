from __future__ import annotations

from typing import Any

_WEB_SUMMARY_DAYS = 30
_VALID_GROUP_BY = {"flow_type", "agent", "model", "session_id"}


async def web_cost_summary(pool: Any, *, days: int = _WEB_SUMMARY_DAYS) -> dict:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent,
                   COUNT(*)::int                AS calls,
                   SUM(prompt_tokens)::int      AS prompt_tokens,
                   SUM(completion_tokens)::int  AS completion_tokens,
                   SUM(total_tokens)::int       AS total_tokens,
                   SUM(cost_usd)                AS cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            GROUP BY agent
            ORDER BY SUM(cost_usd) DESC NULLS LAST
            """,
            days,
        )
        totals = await conn.fetchrow(
            """
            SELECT COUNT(*)::int           AS total_calls,
                   SUM(total_tokens)::int  AS total_tokens,
                   SUM(cost_usd)           AS total_cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            """,
            days,
        )
        daily_rows = await conn.fetch(
            """
            SELECT DATE(created_at)::text  AS day,
                   COUNT(*)::int           AS calls,
                   SUM(cost_usd)           AS cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
            """,
            days,
        )

    by_agent = {
        row["agent"]: {
            "usd": float(row["cost_usd"] or 0),
            "tokens": row["total_tokens"] or 0,
            "calls": row["calls"] or 0,
            "prompt_tokens": row["prompt_tokens"] or 0,
            "completion_tokens": row["completion_tokens"] or 0,
        }
        for row in rows
    }
    by_day = [
        {
            "date": row["day"],
            "usd": float(row["cost_usd"] or 0),
            "calls": row["calls"] or 0,
        }
        for row in daily_rows
    ]
    return {
        "total_usd": float(totals["total_cost_usd"] or 0),
        "total_tokens": int(totals["total_tokens"] or 0),
        "total_calls": int(totals["total_calls"] or 0),
        "by_agent": by_agent,
        "by_day": by_day,
        "period": f"Last {days} days",
    }


async def cost_detail(pool: Any, *, days: int, group_by: str) -> dict:
    if group_by not in _VALID_GROUP_BY:
        raise ValueError(f"group_by must be one of {sorted(_VALID_GROUP_BY)}")

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                {group_by}                   AS grp,
                COUNT(*)::int                AS calls,
                SUM(prompt_tokens)::int      AS prompt_tokens,
                SUM(completion_tokens)::int  AS completion_tokens,
                SUM(total_tokens)::int       AS total_tokens,
                SUM(cost_usd)                AS cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            GROUP BY {group_by}
            ORDER BY SUM(total_tokens) DESC
            """,
            days,
        )
        totals = await conn.fetchrow(
            """
            SELECT
                COUNT(*)::int       AS total_calls,
                SUM(total_tokens)   AS total_tokens,
                SUM(cost_usd)       AS total_cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            """,
            days,
        )

    buckets = [
        {
            "group": row["grp"],
            "calls": row["calls"],
            "prompt_tokens": row["prompt_tokens"],
            "completion_tokens": row["completion_tokens"],
            "total_tokens": row["total_tokens"],
            "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None,
        }
        for row in rows
    ]

    return {
        "period_days": days,
        "group_by": group_by,
        "total_calls": totals["total_calls"] or 0,
        "total_tokens": int(totals["total_tokens"] or 0),
        "total_cost_usd": float(totals["total_cost_usd"]) if totals["total_cost_usd"] is not None else None,
        "buckets": buckets,
    }


async def build_cost_summary(container: Any) -> str:
    async with container.pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT agent,
                   COUNT(*)::int        AS run_count,
                   SUM(total_tokens)    AS total_tokens,
                   SUM(cost_usd)        AS cost_usd
            FROM llm_cost_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            GROUP BY agent
            ORDER BY SUM(cost_usd) DESC NULLS LAST
            """
        )
        total = await conn.fetchrow(
            """
            SELECT SUM(cost_usd) AS total_cost, COUNT(*)::int AS total_runs
            FROM llm_cost_log
            WHERE created_at >= NOW() - INTERVAL '7 days'
            """
        )

    if not rows and (not total or not total["total_runs"]):
        return "No LLM cost data for the past 7 days."

    total_cost = float(total["total_cost"] or 0)
    total_runs = total["total_runs"] or 0
    lines = [f"Cost summary — last 7 days: ${total_cost:.4f} across {total_runs} runs"]
    for row in rows:
        cost = float(row["cost_usd"] or 0)
        lines.append(f"  • {row['agent']}: {row['run_count']} runs, ${cost:.4f}")
    return "\n".join(lines)
