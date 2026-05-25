from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import asyncpg

from ze.goals.types import (
    Goal,
    GoalLearning,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
    VerificationGate,
)
from ze.logging import get_logger

log = get_logger(__name__)


def _goal_from_row(row) -> Goal:
    return Goal(
        id=row["id"],
        title=row["title"],
        objective=row["objective"],
        success_condition=row["success_condition"],
        time_horizon=row["time_horizon"],
        status=GoalStatus(row["status"]),
        type=row["type"],
        learnings=row["learnings"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _milestone_from_row(row) -> Milestone:
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


class GoalStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
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
        """Goals eligible for the advance sweep (excludes awaiting_gate and planning)."""
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
        """Delete all PENDING milestones for a goal and insert replacements."""
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

    async def replace_pending_gates(
        self,
        goal_id: UUID,
        new_gates: list[VerificationGate],
    ) -> list[VerificationGate]:
        """Delete all PENDING gates for a goal and insert replacements."""
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
