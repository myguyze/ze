from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids
from ze_seed.narrative.ids import (
    GATE_IDS,
    GATE_PT_1,
    GATE_SP_1,
    GOAL_IDS,
    GOAL_PORTUGUESE,
    GOAL_SIDE_PROJECT,
    GOAL_SLEEP,
    LEARNING_IDS,
    MS_PT_1,
    MS_PT_2,
    MS_PT_3,
    MS_PT_4,
    MS_SL_1,
    MS_SL_2,
    MS_SP_1,
    MS_SP_2,
    MILESTONE_IDS,
    TRACE_IDS,
    TRACE_PT_1,
    TRACE_PT_2,
)


async def _clear_automation(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "goal_execution_traces", TRACE_IDS)
        await delete_by_ids(conn, "goal_learnings", LEARNING_IDS)
        await delete_by_ids(conn, "goal_gates", GATE_IDS)
        await delete_by_ids(conn, "goal_milestones", MILESTONE_IDS)
        await delete_by_ids(conn, "goals", GOAL_IDS)


async def _apply_automation(ctx: SeedContext) -> int:
    now = datetime.now(timezone.utc)
    count = 0
    async with ctx.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO goals (id, title, objective, success_condition, time_horizon, status, type, learnings)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            GOAL_PORTUGUESE,
            "Reach B1 Portuguese",
            "Achieve conversational B1 level in European Portuguese through structured study and practice",
            "Can hold a 15-minute conversation on everyday topics with tutor Ana without switching to English",
            "3 months",
            "awaiting_gate",
            "learning",
            "Duolingo streak helps daily habit; conversation practice is the bottleneck",
        )
        await conn.execute(
            """
            INSERT INTO goals (id, title, objective, success_condition, time_horizon, status, type, learnings, retrospective_text)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO NOTHING
            """,
            GOAL_SIDE_PROJECT,
            "Ship side project MVP",
            "Launch LedgerLite personal finance tracker to a small audience",
            "Landing page live, 10 beta users signed up, core CSV import working",
            "6 weeks",
            "completed",
            "project",
            "Indie hacker communities respond well to build-in-public posts",
            "Shipped on time. Product Hunt launch drove most signups. CSV import was the most requested feature.",
        )
        await conn.execute(
            """
            INSERT INTO goals (id, title, objective, success_condition, time_horizon, status, type, learnings)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            GOAL_SLEEP,
            "Improve sleep routine",
            "Consistently sleep before midnight on weeknights",
            "5 of 7 weeknights asleep before midnight for 4 consecutive weeks",
            "8 weeks",
            "planning",
            "health",
            "",
        )
        count += 3

        milestones = [
            (MS_PT_1, GOAL_PORTUGUESE, "Complete A2 assessment", "Take formal A2 assessment with tutor", 1, "companion", "completed", "Passed A2 with strong grammar scores"),
            (MS_PT_2, GOAL_PORTUGUESE, "Master past tense", "Practice pretérito perfeito and imperfeito", 2, "companion", "completed", "Comfortable with daily conversation past tense"),
            (MS_PT_3, GOAL_PORTUGUESE, "Weekly conversation practice", "30-min conversation sessions twice weekly", 3, "companion", "in_progress", ""),
            (MS_PT_4, GOAL_PORTUGUESE, "B1 mock exam", "Complete B1 practice exam with tutor feedback", 4, "research", "pending", ""),
            (MS_SP_1, GOAL_SIDE_PROJECT, "Build MVP features", "CSV import, categorization, monthly summary", 1, "research", "completed", "Core features shipped"),
            (MS_SP_2, GOAL_SIDE_PROJECT, "Launch publicly", "Landing page, Product Hunt, community posts", 2, "research", "completed", "10 beta users acquired"),
            (MS_SL_1, GOAL_SLEEP, "Track sleep for 2 weeks", "Log bedtime and wake time daily", 1, "companion", "pending", ""),
            (MS_SL_2, GOAL_SLEEP, "Establish wind-down routine", "No screens after 11pm, read for 20 min", 2, "companion", "pending", ""),
        ]
        for mid, gid, title, desc, seq, hint, status, output in milestones:
            completed_at = now - timedelta(days=7) if status == "completed" else None
            await conn.execute(
                """
                INSERT INTO goal_milestones
                    (id, goal_id, title, description, sequence, agent_hint, intent, status, output, completed_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'execute', $7, $8, $9)
                ON CONFLICT (id) DO NOTHING
                """,
                mid, gid, title, desc, seq, hint, status, output, completed_at,
            )
            count += 1

        await conn.execute(
            """
            INSERT INTO goal_gates
                (id, goal_id, after_sequence, title, status, context_summary, plan_summary, fired_at)
            VALUES ($1, $2, 2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO NOTHING
            """,
            GATE_PT_1,
            GOAL_PORTUGUESE,
            "Review Portuguese progress after past tense milestone",
            "awaiting_approval",
            "Completed A2 and past tense milestones. Tutor Ana recommends increasing conversation practice before B1 mock exam.",
            "Next: focus on 2x weekly conversation sessions, then schedule B1 mock exam in 3 weeks.",
            now - timedelta(days=2),
        )
        await conn.execute(
            """
            INSERT INTO goal_gates
                (id, goal_id, after_sequence, title, status, context_summary, plan_summary, fired_at, resolved_at)
            VALUES ($1, $2, 2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            GATE_SP_1,
            GOAL_SIDE_PROJECT,
            "Review MVP before public launch",
            "approved",
            "MVP features complete. Beta feedback positive on CSV import.",
            "Proceed with Product Hunt launch and community outreach.",
            now - timedelta(days=30),
            now - timedelta(days=29),
        )
        count += 2

        await conn.execute(
            """
            INSERT INTO goal_learnings (id, goal_id, content, source)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            LEARNING_IDS[0],
            GOAL_PORTUGUESE,
            "Conversation practice is more effective than grammar drills at A2→B1 transition",
            "milestone_retrospective",
        )
        await conn.execute(
            """
            INSERT INTO goal_learnings (id, goal_id, content, source)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (id) DO NOTHING
            """,
            LEARNING_IDS[1],
            GOAL_PORTUGUESE,
            "Duolingo maintains daily habit but does not build conversational fluency alone",
            "executor",
        )
        count += 2

        await conn.execute(
            """
            INSERT INTO goal_execution_traces
                (id, milestone_id, goal_id, seq, tool_name, args, result, duration_ms, success)
            VALUES ($1, $2, $3, 1, 'openrouter:web_search', $4, $5, 1200, true)
            ON CONFLICT (id) DO NOTHING
            """,
            TRACE_PT_1,
            MS_PT_1,
            GOAL_PORTUGUESE,
            json.dumps({"query": "European Portuguese A2 assessment criteria"}),
            "A2 requires 1000 words, basic past tense, and everyday conversation ability",
        )
        await conn.execute(
            """
            INSERT INTO goal_execution_traces
                (id, milestone_id, goal_id, seq, tool_name, args, result, duration_ms, success)
            VALUES ($1, $2, $3, 1, 'openrouter:web_search', $4, $5, 980, true)
            ON CONFLICT (id) DO NOTHING
            """,
            TRACE_PT_2,
            MS_PT_2,
            GOAL_PORTUGUESE,
            json.dumps({"query": "Portuguese past tense exercises B1"}),
            "Found Practice Portuguese podcast episodes on pretérito perfeito",
        )
        count += 2

    return count


def automation_seed_domains() -> list[SeedDomain]:
    return [
        SeedDomain("automation.dev", seed_order=20, clear=_clear_automation, apply=_apply_automation),
    ]
