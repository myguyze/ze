from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids
from ze_seed.narrative.ids import (
    EXECUTION_IDS,
    EXEC_HEALTH_LOOP_FAIL,
    EXEC_INV_FOUND,
    EXEC_INV_NONE,
    EXEC_LL_1,
    EXEC_MB_1,
    EXEC_MB_2,
    EXEC_PT_FAIL,
    EXEC_PT_OK_1,
    EXEC_PT_OK_2,
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
    TRACE_PT_3,
    TRACE_SP_1,
    TRACE_SP_2,
    WF_DEPLOY_HEALTH_CHECK,
    WF_INVOICE_CHECK,
    WF_LEDGERLITE_DIGEST,
    WF_MORNING_BRIEFING,
    WF_PORTUGUESE_CHECKIN,
    WORKFLOW_IDS,
)


async def _clear_automation(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "workflow_executions", EXECUTION_IDS)
        await delete_by_ids(conn, "workflows", WORKFLOW_IDS)
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
        await conn.execute(
            """
            INSERT INTO goal_execution_traces
                (id, milestone_id, goal_id, seq, tool_name, args, result, duration_ms, success)
            VALUES ($1, $2, $3, 1, 'companion', $4, $5, 2100, true)
            ON CONFLICT (id) DO NOTHING
            """,
            TRACE_PT_3,
            MS_PT_3,
            GOAL_PORTUGUESE,
            json.dumps({"task": "Schedule conversation practice sessions"}),
            "Booked two 30-min sessions with Ana for this week",
        )
        await conn.execute(
            """
            INSERT INTO goal_execution_traces
                (id, milestone_id, goal_id, seq, tool_name, args, result, duration_ms, success)
            VALUES ($1, $2, $3, 1, 'research', $4, $5, 3400, true)
            ON CONFLICT (id) DO NOTHING
            """,
            TRACE_SP_1,
            MS_SP_1,
            GOAL_SIDE_PROJECT,
            json.dumps({"task": "Implement CSV import and categorization"}),
            "CSV import handles European date formats; auto-categorization at 82% accuracy",
        )
        await conn.execute(
            """
            INSERT INTO goal_execution_traces
                (id, milestone_id, goal_id, seq, tool_name, args, result, duration_ms, success)
            VALUES ($1, $2, $3, 1, 'openrouter:web_search', $4, $5, 1800, true)
            ON CONFLICT (id) DO NOTHING
            """,
            TRACE_SP_2,
            MS_SP_2,
            GOAL_SIDE_PROJECT,
            json.dumps({"query": "Product Hunt launch checklist indie SaaS"}),
            "Drafted launch post and scheduled for Tuesday 8am PT",
        )
        count += 5

        pt_steps = json.dumps([
            {"task": "Check Duolingo streak and weekly XP", "agent_hint": "companion", "intent": "execute"},
            {"task": "Summarize tutor feedback from last session", "agent_hint": "companion", "intent": "execute"},
            {"task": "Suggest one B1 practice resource", "agent_hint": "research", "intent": "execute"},
        ])
        mb_steps = json.dumps([
            {"task": "List today's calendar events", "agent_hint": "calendar", "intent": "execute"},
            {"task": "Surface pending reminders", "agent_hint": "calendar", "intent": "execute"},
            {"task": "Draft a one-paragraph day overview", "agent_hint": "companion", "intent": "execute"},
        ])
        ll_steps = json.dumps([
            {"task": "Collect beta user feedback from the past week", "agent_hint": "research", "intent": "execute"},
            {"task": "Summarize signups and active users", "agent_hint": "research", "intent": "execute"},
            {"task": "Draft a build-in-public update post", "agent_hint": "companion", "intent": "execute"},
        ])
        invoice_steps = json.dumps([
            {
                "task": "Check inbox for an Acme invoice",
                "agent_hint": "messenger",
                "intent": "execute",
                "id": "s0",
                "branches": [
                    {"condition": "an Acme invoice arrived", "to": "s1"},
                    {"condition": "no Acme invoice arrived", "to": "s2"},
                ],
            },
            {
                "task": "Forward the invoice to accounting@example.com",
                "agent_hint": "messenger",
                "intent": "execute",
                "id": "s1",
            },
            {
                "task": "Log that no invoice arrived today",
                "agent_hint": "companion",
                "intent": "execute",
                "id": "s2",
            },
        ])
        health_check_steps = json.dumps([
            {
                "task": "Ping the LedgerLite health endpoint",
                "agent_hint": "research",
                "intent": "execute",
                "id": "s0",
                "branches": [
                    {"condition": "endpoint is healthy", "to": "END"},
                    {"condition": "endpoint is still failing", "to": "s0"},
                ],
            },
        ])

        await conn.execute(
            """
            INSERT INTO workflows
                (id, name, description, steps, schedule, enabled,
                 last_run_at, next_run_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, true, $6, $7, $8, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            WF_PORTUGUESE_CHECKIN,
            "Weekly Portuguese check-in",
            "Review study progress, tutor notes, and suggest practice resources every Monday morning",
            pt_steps,
            "0 9 * * 1",
            now - timedelta(days=3),
            now + timedelta(days=4),
            now - timedelta(days=60),
        )
        await conn.execute(
            """
            INSERT INTO workflows
                (id, name, description, steps, schedule, enabled,
                 last_run_at, next_run_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, true, $6, $7, $8, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            WF_MORNING_BRIEFING,
            "Weekday morning briefing",
            "Summarize today's calendar, reminders, and priorities before work starts",
            mb_steps,
            "0 7 * * 1-5",
            now - timedelta(hours=10),
            now + timedelta(hours=14),
            now - timedelta(days=45),
        )
        await conn.execute(
            """
            INSERT INTO workflows
                (id, name, description, steps, schedule, enabled,
                 last_run_at, next_run_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, false, $6, NULL, $7, $7)
            ON CONFLICT (id) DO NOTHING
            """,
            WF_LEDGERLITE_DIGEST,
            "LedgerLite weekly digest",
            "Compile beta metrics and draft a build-in-public update every Friday evening",
            ll_steps,
            "0 18 * * 5",
            now - timedelta(days=7),
            now - timedelta(days=30),
        )
        await conn.execute(
            """
            INSERT INTO workflows
                (id, name, description, steps, schedule, enabled,
                 last_run_at, next_run_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, true, $6, $7, $8, $8)
            ON CONFLICT (id) DO NOTHING
            """,
            WF_INVOICE_CHECK,
            "Invoice inbox check",
            "Check inbox for an Acme invoice; if one arrived, forward it to accounting, otherwise log that none arrived",
            invoice_steps,
            "0 8 * * *",
            now - timedelta(hours=16),
            now + timedelta(hours=8),
            now - timedelta(days=14),
        )
        await conn.execute(
            """
            INSERT INTO workflows
                (id, name, description, steps, schedule, enabled,
                 last_run_at, next_run_at, created_at, updated_at)
            VALUES ($1, $2, $3, $4::jsonb, $5, false, $6, NULL, $7, $7)
            ON CONFLICT (id) DO NOTHING
            """,
            WF_DEPLOY_HEALTH_CHECK,
            "Deploy health check",
            "Poll the LedgerLite health endpoint after a deploy, retrying until it reports healthy",
            health_check_steps,
            None,
            now - timedelta(days=5),
            now - timedelta(days=5),
        )
        count += 5

        pt_ok_1_results = json.dumps([
            {
                "step_index": 0,
                "task": "Check Duolingo streak and weekly XP",
                "output": "47-day streak; 340 XP this week (+12% vs last week)",
                "success": True,
                "error": None,
                "duration_ms": 420,
            },
            {
                "step_index": 1,
                "task": "Summarize tutor feedback from last session",
                "output": "Ana noted strong past tense usage; subjunctive in 'se' clauses still hesitant",
                "success": True,
                "error": None,
                "duration_ms": 890,
            },
            {
                "step_index": 2,
                "task": "Suggest one B1 practice resource",
                "output": "Practice Portuguese podcast episode 42 covers subjunctive triggers",
                "success": True,
                "error": None,
                "duration_ms": 1100,
            },
        ])
        pt_ok_2_results = json.dumps([
            {
                "step_index": 0,
                "task": "Check Duolingo streak and weekly XP",
                "output": "40-day streak; 290 XP this week",
                "success": True,
                "error": None,
                "duration_ms": 380,
            },
            {
                "step_index": 1,
                "task": "Summarize tutor feedback from last session",
                "output": "Good progress on pretérito imperfeito; needs more conversation practice",
                "success": True,
                "error": None,
                "duration_ms": 750,
            },
            {
                "step_index": 2,
                "task": "Suggest one B1 practice resource",
                "output": "LingQ intermediate story 'O Café da Manhã' recommended",
                "success": True,
                "error": None,
                "duration_ms": 920,
            },
        ])
        pt_fail_results = json.dumps([
            {
                "step_index": 0,
                "task": "Check Duolingo streak and weekly XP",
                "output": "Streak maintained at 35 days",
                "success": True,
                "error": None,
                "duration_ms": 400,
            },
            {
                "step_index": 1,
                "task": "Summarize tutor feedback from last session",
                "output": "",
                "success": False,
                "error": "Could not retrieve tutoring notes — session was rescheduled",
                "duration_ms": 120,
            },
        ])
        mb_results = json.dumps([
            {
                "step_index": 0,
                "task": "List today's calendar events",
                "output": "Focus block 9-11am, standup 10am, tutoring 6pm",
                "success": True,
                "error": None,
                "duration_ms": 310,
            },
            {
                "step_index": 1,
                "task": "Surface pending reminders",
                "output": "Prep standup notes for Marco; dentist prep in 5 days",
                "success": True,
                "error": None,
                "duration_ms": 180,
            },
            {
                "step_index": 2,
                "task": "Draft a one-paragraph day overview",
                "output": "Busy day with focus time morning, standup mid-morning, Portuguese tutoring evening.",
                "success": True,
                "error": None,
                "duration_ms": 640,
            },
        ])
        ll_results = json.dumps([
            {
                "step_index": 0,
                "task": "Collect beta user feedback from the past week",
                "output": "3 feature requests for CSV date formats; 1 bug report on category colors",
                "success": True,
                "error": None,
                "duration_ms": 1500,
            },
            {
                "step_index": 1,
                "task": "Summarize signups and active users",
                "output": "12 total signups, 7 active this week (+2 from last week)",
                "success": True,
                "error": None,
                "duration_ms": 800,
            },
            {
                "step_index": 2,
                "task": "Draft a build-in-public update post",
                "output": "Draft post ready — highlights CSV import fix and weekly active user growth",
                "success": True,
                "error": None,
                "duration_ms": 2200,
            },
        ])

        invoice_found_results = json.dumps([
            {
                "step_index": 0,
                "task": "Check inbox for an Acme invoice",
                "output": "Found invoice #4471 from Acme for $2,340, received this morning",
                "success": True,
                "error": None,
                "duration_ms": 640,
                "step_id": "s0",
                "branch_taken": "an Acme invoice arrived",
            },
            {
                "step_index": 1,
                "task": "Forward the invoice to accounting@example.com",
                "output": "Forwarded invoice #4471 to accounting@example.com",
                "success": True,
                "error": None,
                "duration_ms": 210,
                "step_id": "s1",
                "branch_taken": None,
            },
        ])
        invoice_none_results = json.dumps([
            {
                "step_index": 0,
                "task": "Check inbox for an Acme invoice",
                "output": "No Acme invoice in the inbox today",
                "success": True,
                "error": None,
                "duration_ms": 510,
                "step_id": "s0",
                "branch_taken": "no Acme invoice arrived",
            },
            {
                "step_index": 1,
                "task": "Log that no invoice arrived today",
                "output": "Logged: no Acme invoice today",
                "success": True,
                "error": None,
                "duration_ms": 90,
                "step_id": "s2",
                "branch_taken": None,
            },
        ])
        health_loop_fail_results = json.dumps([
            {
                "step_index": i,
                "task": "Ping the LedgerLite health endpoint",
                "output": "Health endpoint returned 503 Service Unavailable",
                "success": True,
                "error": None,
                "duration_ms": 300 + i * 50,
                "step_id": "s0",
                "branch_taken": "endpoint is still failing",
            }
            for i in range(4)
        ])

        executions = [
            (
                EXEC_PT_OK_1,
                WF_PORTUGUESE_CHECKIN,
                "completed",
                pt_ok_1_results,
                None,
                "Duolingo streak at 47 days. Tutor feedback positive on past tense; subjunctive practice recommended.",
                now - timedelta(days=10),
                now - timedelta(days=10) + timedelta(minutes=3),
            ),
            (
                EXEC_PT_OK_2,
                WF_PORTUGUESE_CHECKIN,
                "completed",
                pt_ok_2_results,
                None,
                "Steady progress — conversation practice identified as the main gap before B1 mock exam.",
                now - timedelta(days=17),
                now - timedelta(days=17) + timedelta(minutes=2),
            ),
            (
                EXEC_PT_FAIL,
                WF_PORTUGUESE_CHECKIN,
                "failed",
                pt_fail_results,
                "Tutoring session was rescheduled — could not summarize feedback",
                None,
                now - timedelta(days=24),
                now - timedelta(days=24) + timedelta(minutes=1),
            ),
            (
                EXEC_MB_1,
                WF_MORNING_BRIEFING,
                "completed",
                mb_results,
                None,
                "Today: focus block, standup, tutoring. Two reminders pending.",
                now - timedelta(days=1),
                now - timedelta(days=1) + timedelta(minutes=2),
            ),
            (
                EXEC_MB_2,
                WF_MORNING_BRIEFING,
                "completed",
                mb_results,
                None,
                "Standard weekday — focus time protected, standup and tutoring on calendar.",
                now - timedelta(days=2),
                now - timedelta(days=2) + timedelta(minutes=2),
            ),
            (
                EXEC_LL_1,
                WF_LEDGERLITE_DIGEST,
                "completed",
                ll_results,
                None,
                "12 signups, 7 active users. CSV date format fix is top request.",
                now - timedelta(days=7),
                now - timedelta(days=7) + timedelta(minutes=5),
            ),
            (
                EXEC_INV_FOUND,
                WF_INVOICE_CHECK,
                "completed",
                invoice_found_results,
                None,
                "Found Acme invoice #4471 and forwarded it to accounting.",
                now - timedelta(hours=16),
                now - timedelta(hours=16) + timedelta(minutes=1),
            ),
            (
                EXEC_INV_NONE,
                WF_INVOICE_CHECK,
                "completed",
                invoice_none_results,
                None,
                "No Acme invoice today; logged for the record.",
                now - timedelta(hours=40),
                now - timedelta(hours=40) + timedelta(minutes=1),
            ),
            (
                EXEC_HEALTH_LOOP_FAIL,
                WF_DEPLOY_HEALTH_CHECK,
                "failed",
                health_loop_fail_results,
                "Loop limit exceeded for step s0 (Ping the LedgerLite health endpoint): "
                "executed 4 times (1 initial + 3 revisits); cannot revisit again.",
                None,
                now - timedelta(days=5),
                now - timedelta(days=5) + timedelta(minutes=2),
            ),
        ]
        for exec_id, wf_id, status, step_results, error, summary, started, completed in executions:
            await conn.execute(
                """
                INSERT INTO workflow_executions
                    (id, workflow_id, status, step_results, error, summary,
                     started_at, completed_at, created_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $7)
                ON CONFLICT (id) DO NOTHING
                """,
                exec_id,
                wf_id,
                status,
                step_results,
                error,
                summary,
                started,
                completed,
            )
            count += 1

    return count


def automation_seed_domains() -> list[SeedDomain]:
    return [
        SeedDomain("automation.dev", seed_order=20, clear=_clear_automation, apply=_apply_automation),
    ]
