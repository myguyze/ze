from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ze_core.db import DBPool
import json

from ze_personal.goals.types import (
    ExecutionTrace,
    Goal,
    GoalLearning,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
    PriorMilestoneOutput,
    StuckGoal,
    VerificationGate,
)
from ze_core.logging import get_logger

log = get_logger(__name__)


def _goal_from_row(row) -> Goal:
    keys = row.keys()
    return Goal(
        id=row["id"],
        title=row["title"],
        objective=row["objective"],
        success_condition=row["success_condition"],
        time_horizon=row["time_horizon"],
        status=GoalStatus(row["status"]),
        type=row["type"],
        learnings=row["learnings"],
        retrospective_text=row["retrospective_text"] if "retrospective_text" in keys else None,
        last_stuck_alert_at=row["last_stuck_alert_at"] if "last_stuck_alert_at" in keys else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _milestone_from_row(row) -> Milestone:
    keys = row.keys()
    return Milestone(
        id=row["id"],
        goal_id=row["goal_id"],
        title=row["title"],
        description=row["description"],
        sequence=row["sequence"],
        agent_hint=row["agent_hint"],
        intent=row["intent"],
        status=MilestoneStatus(row["status"]),
        output=row["output"],
        reuse_hint=row["reuse_hint"] if "reuse_hint" in keys else "",
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )


def _gate_from_row(row) -> VerificationGate:
    return VerificationGate(
        id=row["id"],
        goal_id=row["goal_id"],
        after_sequence=row["after_sequence"],
        title=row["title"],
        status=GateStatus(row["status"]),
        context_summary=row["context_summary"],
        plan_summary=row["plan_summary"],
        user_feedback=row["user_feedback"],
        fired_at=row["fired_at"],
        resolved_at=row["resolved_at"],
        created_at=row["created_at"],
    )


def _learning_from_row(row) -> GoalLearning:
    return GoalLearning(
        id=row["id"],
        goal_id=row["goal_id"],
        content=row["content"],
        source=row["source"],
        created_at=row["created_at"],
    )


class PostgresGoalStore:
    def __init__(self, pool: DBPool) -> None:
        self._pool = pool

    # ── Goals ──────────────────────────────────────────────────────────────────

    async def create_goal(self, goal: Goal) -> Goal:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO goals (title, objective, success_condition, time_horizon, status, type, learnings)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                goal.title,
                goal.objective,
                goal.success_condition,
                goal.time_horizon,
                goal.status.value,
                goal.type,
                goal.learnings,
            )
        result = _goal_from_row(row)
        log.info("goal_created", goal_id=str(result.id), title=goal.title)
        return result

    async def get_goal(self, goal_id: UUID) -> Goal | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM goals WHERE id = $1", goal_id)
        return _goal_from_row(row) if row else None

    async def list_active(self) -> list[Goal]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM goals WHERE status IN ('active', 'awaiting_gate') ORDER BY created_at ASC"
            )
        return [_goal_from_row(r) for r in rows]

    async def list_for_advance(self) -> list[Goal]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM goals WHERE status = 'active' ORDER BY created_at ASC"
            )
        return [_goal_from_row(r) for r in rows]

    async def list_all(self) -> list[Goal]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM goals ORDER BY created_at DESC")
        return [_goal_from_row(r) for r in rows]

    async def update_status(self, goal_id: UUID, status: GoalStatus) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE goals SET status = $1, updated_at = NOW() WHERE id = $2",
                status.value, goal_id,
            )

    async def append_learnings(self, goal_id: UUID, text: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE goals
                SET learnings = CASE WHEN learnings = '' THEN $1 ELSE learnings || E'\n' || $1 END,
                    updated_at = NOW()
                WHERE id = $2
                """,
                text, goal_id,
            )

    # ── Milestones ─────────────────────────────────────────────────────────────

    async def create_milestone(self, m: Milestone) -> Milestone:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO goal_milestones (goal_id, title, description, sequence, agent_hint, intent, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING *
                """,
                m.goal_id, m.title, m.description, m.sequence,
                m.agent_hint, m.intent, m.status.value,
            )
        return _milestone_from_row(row)

    async def list_milestones(self, goal_id: UUID) -> list[Milestone]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM goal_milestones WHERE goal_id = $1 ORDER BY sequence ASC",
                goal_id,
            )
        return [_milestone_from_row(r) for r in rows]

    async def update_milestone(
        self,
        milestone_id: UUID,
        status: MilestoneStatus,
        output: str = "",
    ) -> None:
        completed_at = datetime.now(timezone.utc) if status == MilestoneStatus.COMPLETED else None
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE goal_milestones
                SET status = $1, output = $2, completed_at = $3
                WHERE id = $4
                """,
                status.value, output, completed_at, milestone_id,
            )

    async def replace_pending_milestones(
        self,
        goal_id: UUID,
        new_milestones: list[Milestone],
    ) -> list[Milestone]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM goal_milestones WHERE goal_id = $1 AND status = 'pending'",
                    goal_id,
                )
                results = []
                for m in new_milestones:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO goal_milestones (goal_id, title, description, sequence, agent_hint, intent, status)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        RETURNING *
                        """,
                        goal_id, m.title, m.description, m.sequence,
                        m.agent_hint, m.intent, m.status.value,
                    )
                    results.append(_milestone_from_row(row))
        return results

    # ── Gates ──────────────────────────────────────────────────────────────────

    async def create_gate(self, gate: VerificationGate) -> VerificationGate:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO goal_gates (goal_id, after_sequence, title, status)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                gate.goal_id, gate.after_sequence, gate.title, gate.status.value,
            )
        return _gate_from_row(row)

    async def get_pending_gate(self, goal_id: UUID) -> VerificationGate | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM goal_gates
                WHERE goal_id = $1 AND status IN ('pending', 'awaiting_approval')
                ORDER BY after_sequence ASC
                LIMIT 1
                """,
                goal_id,
            )
        return _gate_from_row(row) if row else None

    async def get_gate(self, gate_id: UUID) -> VerificationGate | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM goal_gates WHERE id = $1", gate_id)
        return _gate_from_row(row) if row else None

    async def fire_gate(
        self,
        gate_id: UUID,
        context_summary: str,
        plan_summary: str,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE goal_gates
                SET status = 'awaiting_approval',
                    context_summary = $1,
                    plan_summary = $2,
                    fired_at = NOW()
                WHERE id = $3
                """,
                context_summary, plan_summary, gate_id,
            )

    async def resolve_gate(
        self,
        gate_id: UUID,
        status: GateStatus,
        user_feedback: str = "",
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE goal_gates
                SET status = $1, user_feedback = $2, resolved_at = NOW()
                WHERE id = $3
                """,
                status.value, user_feedback, gate_id,
            )

    async def replace_pending_gates(
        self,
        goal_id: UUID,
        new_gates: list[VerificationGate],
    ) -> list[VerificationGate]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM goal_gates WHERE goal_id = $1 AND status = 'pending'",
                    goal_id,
                )
                results = []
                for g in new_gates:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO goal_gates (goal_id, after_sequence, title, status)
                        VALUES ($1, $2, $3, $4)
                        RETURNING *
                        """,
                        goal_id, g.after_sequence, g.title, g.status.value,
                    )
                    results.append(_gate_from_row(row))
        return results

    # ── Learnings ──────────────────────────────────────────────────────────────

    async def add_learning(self, learning: GoalLearning) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO goal_learnings (goal_id, content, source)
                VALUES ($1, $2, $3)
                """,
                learning.goal_id, learning.content, learning.source,
            )

    async def list_learnings(self, goal_id: UUID) -> list[GoalLearning]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM goal_learnings WHERE goal_id = $1 ORDER BY created_at DESC",
                goal_id,
            )
        return [_learning_from_row(r) for r in rows]

    # ── Execution traces ───────────────────────────────────────────────────────

    async def save_traces(self, traces: list[ExecutionTrace]) -> None:
        if not traces:
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for t in traces:
                    await conn.execute(
                        """
                        INSERT INTO goal_execution_traces
                            (milestone_id, goal_id, seq, tool_name, args, result, duration_ms, success, error)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        t.milestone_id, t.goal_id, t.seq, t.tool_name,
                        json.dumps(t.args), t.result, t.duration_ms, t.success, t.error,
                    )

    async def list_traces(self, milestone_id: UUID) -> list[ExecutionTrace]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM goal_execution_traces WHERE milestone_id = $1 ORDER BY seq ASC",
                milestone_id,
            )
        return [
            ExecutionTrace(
                id=r["id"],
                milestone_id=r["milestone_id"],
                goal_id=r["goal_id"],
                seq=r["seq"],
                tool_name=r["tool_name"],
                args=json.loads(r["args"]) if isinstance(r["args"], str) else dict(r["args"]),
                result=r["result"],
                duration_ms=r["duration_ms"],
                success=r["success"],
                error=r["error"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ── Failure counters ───────────────────────────────────────────────────────

    async def increment_consecutive_failures(self, goal_id: UUID) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE goals
                SET consecutive_failures = consecutive_failures + 1, updated_at = NOW()
                WHERE id = $1
                RETURNING consecutive_failures
                """,
                goal_id,
            )
        return row["consecutive_failures"] if row else 0

    async def reset_consecutive_failures(self, goal_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE goals SET consecutive_failures = 0, updated_at = NOW() WHERE id = $1",
                goal_id,
            )

    async def increment_replan_count(self, goal_id: UUID) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE goals
                SET replan_count = replan_count + 1, updated_at = NOW()
                WHERE id = $1
                RETURNING replan_count
                """,
                goal_id,
            )
        return row["replan_count"] if row else 0

    # ── Retrospectives ─────────────────────────────────────────────────────────

    async def save_retrospective(self, goal_id: UUID, text: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE goals SET retrospective_text = $2, updated_at = NOW() WHERE id = $1",
                goal_id,
                text,
            )

    async def list_retrospectives(self, days: int) -> list[Goal]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, objective, success_condition, time_horizon, status,
                       type, learnings, retrospective_text, created_at, updated_at
                FROM goals
                WHERE status = 'completed'
                  AND retrospective_text IS NOT NULL
                  AND updated_at >= now() - ($1 || ' days')::interval
                ORDER BY updated_at DESC
                """,
                str(days),
            )
        return [_goal_from_row(r) for r in rows]

    async def list_active_goal_titles(self) -> list[str]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT title FROM goals WHERE status IN ('active', 'planning', 'awaiting_gate', 'paused')"
            )
        return [r["title"] for r in rows]

    # ── Stuck goal detection ───────────────────────────────────────────────────

    async def list_stuck(
        self,
        idle_days: int,
        alert_cooldown_days: int,
    ) -> list[StuckGoal]:
        async with self._pool.acquire() as conn:
            active_rows = await conn.fetch(
                """
                SELECT
                    g.id, g.title, g.objective, g.success_condition, g.time_horizon,
                    g.status, g.type, g.learnings, g.retrospective_text,
                    g.last_stuck_alert_at, g.created_at, g.updated_at,
                    MAX(m.completed_at) AS last_milestone_at,
                    (
                        SELECT title FROM goal_milestones
                        WHERE goal_id = g.id
                          AND status IN ('completed', 'skipped')
                        ORDER BY completed_at DESC NULLS LAST
                        LIMIT 1
                    ) AS last_milestone_title
                FROM goals g
                LEFT JOIN goal_milestones m
                    ON m.goal_id = g.id AND m.status IN ('completed', 'skipped')
                WHERE g.status = 'active'
                  AND (
                      g.last_stuck_alert_at IS NULL
                      OR g.last_stuck_alert_at < now() - ($2 || ' days')::interval
                  )
                GROUP BY g.id
                HAVING
                    (
                        MAX(m.completed_at) IS NULL
                        AND g.created_at < now() - ($1 || ' days')::interval
                    )
                    OR MAX(m.completed_at) < now() - ($1 || ' days')::interval
                ORDER BY COALESCE(MAX(m.completed_at), g.created_at) ASC
                """,
                str(idle_days), str(alert_cooldown_days),
            )

            gate_rows = await conn.fetch(
                """
                SELECT
                    g.id, g.title, g.objective, g.success_condition, g.time_horizon,
                    g.status, g.type, g.learnings, g.retrospective_text,
                    g.last_stuck_alert_at, g.created_at, g.updated_at,
                    vg.id AS gate_id,
                    vg.goal_id AS gate_goal_id,
                    vg.after_sequence,
                    vg.title AS gate_title,
                    vg.status AS gate_status,
                    vg.context_summary,
                    vg.plan_summary,
                    vg.user_feedback,
                    vg.fired_at,
                    vg.resolved_at,
                    vg.created_at AS gate_created_at,
                    EXTRACT(DAY FROM now() - vg.fired_at)::int AS gate_idle_days,
                    (
                        SELECT title FROM goal_milestones
                        WHERE goal_id = g.id
                          AND status IN ('completed', 'skipped')
                        ORDER BY completed_at DESC NULLS LAST
                        LIMIT 1
                    ) AS last_milestone_title
                FROM goals g
                JOIN goal_gates vg
                    ON vg.goal_id = g.id AND vg.status IN ('pending', 'awaiting_approval')
                WHERE g.status = 'awaiting_gate'
                  AND vg.fired_at < now() - ($1 || ' days')::interval
                  AND (
                      g.last_stuck_alert_at IS NULL
                      OR g.last_stuck_alert_at < now() - ($2 || ' days')::interval
                  )
                ORDER BY vg.fired_at ASC
                """,
                str(idle_days), str(alert_cooldown_days),
            )

        results: list[StuckGoal] = []

        for r in active_rows:
            goal = _goal_from_row(r)
            last_at = r["last_milestone_at"]
            ref_dt = last_at if last_at is not None else goal.created_at
            idle = int((datetime.now(timezone.utc) - ref_dt.replace(tzinfo=timezone.utc) if ref_dt.tzinfo is None else datetime.now(timezone.utc) - ref_dt).days)
            results.append(StuckGoal(
                goal=goal,
                kind="active",
                idle_days=idle,
                last_milestone_title=r["last_milestone_title"],
                gate=None,
            ))

        for r in gate_rows:
            goal = _goal_from_row(r)
            gate = VerificationGate(
                id=r["gate_id"],
                goal_id=r["gate_goal_id"],
                after_sequence=r["after_sequence"],
                title=r["gate_title"],
                status=GateStatus(r["gate_status"]),
                context_summary=r["context_summary"],
                plan_summary=r["plan_summary"],
                user_feedback=r["user_feedback"],
                fired_at=r["fired_at"],
                resolved_at=r["resolved_at"],
                created_at=r["gate_created_at"],
            )
            results.append(StuckGoal(
                goal=goal,
                kind="awaiting_gate",
                idle_days=r["gate_idle_days"],
                last_milestone_title=r["last_milestone_title"],
                gate=gate,
            ))

        results.sort(key=lambda sg: sg.idle_days, reverse=True)
        return results

    async def mark_stuck_alerted(self, goal_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE goals SET last_stuck_alert_at = NOW(), updated_at = NOW() WHERE id = $1",
                goal_id,
            )

    # ── Cross-goal output reuse ────────────────────────────────────────────────

    async def list_completed_milestone_summaries(
        self,
        days: int = 90,
        limit: int = 20,
        exclude_goal_id: UUID | None = None,
    ) -> list[PriorMilestoneOutput]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    m.id            AS milestone_id,
                    m.goal_id,
                    g.title         AS goal_title,
                    m.title         AS milestone_title,
                    m.output,
                    GREATEST(0, EXTRACT(EPOCH FROM (NOW() - m.completed_at)) / 86400)::int AS completed_days_ago
                FROM goal_milestones m
                JOIN goals g ON g.id = m.goal_id
                WHERE m.status = 'completed'
                  AND m.output != ''
                  AND m.completed_at > NOW() - ($1 * INTERVAL '1 day')
                  AND ($2::uuid IS NULL OR m.goal_id != $2)
                ORDER BY m.completed_at DESC
                LIMIT $3
                """,
                days, exclude_goal_id, limit,
            )
        return [
            PriorMilestoneOutput(
                goal_id=r["goal_id"],
                goal_title=r["goal_title"],
                milestone_id=r["milestone_id"],
                milestone_title=r["milestone_title"],
                output_snippet=r["output"][:200],
                completed_days_ago=r["completed_days_ago"],
            )
            for r in rows
        ]
