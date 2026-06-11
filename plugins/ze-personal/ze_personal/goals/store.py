from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

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


class GoalStore(Protocol):
    # ── Goals ──────────────────────────────────────────────────────────────────

    async def create_goal(self, goal: Goal) -> Goal: ...

    async def get_goal(self, goal_id: UUID) -> Goal | None: ...

    async def list_active(self) -> list[Goal]: ...

    async def list_for_advance(self) -> list[Goal]:
        """Goals eligible for the advance sweep (status == active)."""
        ...

    async def list_all(self) -> list[Goal]: ...

    async def update_status(self, goal_id: UUID, status: GoalStatus) -> None: ...

    async def append_learnings(self, goal_id: UUID, text: str) -> None: ...

    # ── Milestones ─────────────────────────────────────────────────────────────

    async def create_milestone(self, milestone: Milestone) -> Milestone: ...

    async def list_milestones(self, goal_id: UUID) -> list[Milestone]: ...

    async def update_milestone(
        self,
        milestone_id: UUID,
        status: MilestoneStatus,
        output: str = "",
    ) -> None: ...

    async def replace_pending_milestones(
        self,
        goal_id: UUID,
        new_milestones: list[Milestone],
    ) -> list[Milestone]: ...

    # ── Gates ──────────────────────────────────────────────────────────────────

    async def create_gate(self, gate: VerificationGate) -> VerificationGate: ...

    async def get_pending_gate(self, goal_id: UUID) -> VerificationGate | None: ...

    async def get_gate(self, gate_id: UUID) -> VerificationGate | None: ...

    async def fire_gate(
        self,
        gate_id: UUID,
        context_summary: str,
        plan_summary: str,
    ) -> None: ...

    async def resolve_gate(
        self,
        gate_id: UUID,
        status: GateStatus,
        user_feedback: str = "",
    ) -> None: ...

    async def replace_pending_gates(
        self,
        goal_id: UUID,
        new_gates: list[VerificationGate],
    ) -> list[VerificationGate]: ...

    # ── Learnings ──────────────────────────────────────────────────────────────

    async def add_learning(self, learning: GoalLearning) -> None: ...

    async def list_learnings(self, goal_id: UUID) -> list[GoalLearning]: ...

    # ── Execution traces ───────────────────────────────────────────────────────

    async def save_traces(self, traces: list[ExecutionTrace]) -> None: ...

    async def list_traces(self, milestone_id: UUID) -> list[ExecutionTrace]: ...

    # ── Failure counters ───────────────────────────────────────────────────────

    async def increment_consecutive_failures(self, goal_id: UUID) -> int: ...

    async def reset_consecutive_failures(self, goal_id: UUID) -> None: ...

    async def increment_replan_count(self, goal_id: UUID) -> int: ...

    # ── Retrospectives ─────────────────────────────────────────────────────────

    async def save_retrospective(self, goal_id: UUID, text: str) -> None: ...

    async def list_retrospectives(self, days: int) -> list[Goal]:
        """Return completed goals with retrospective_text set, within the last `days` days."""
        ...

    async def list_active_goal_titles(self) -> list[str]: ...

    # ── Stuck goal detection ───────────────────────────────────────────────────

    async def list_stuck(
        self,
        idle_days: int,
        alert_cooldown_days: int,
    ) -> list[StuckGoal]: ...

    async def mark_stuck_alerted(self, goal_id: UUID) -> None: ...

    # ── Cross-goal output reuse ────────────────────────────────────────────────

    async def list_completed_milestone_summaries(
        self,
        days: int = 90,
        limit: int = 20,
        exclude_goal_id: UUID | None = None,
    ) -> list[PriorMilestoneOutput]: ...
