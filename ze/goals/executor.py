from __future__ import annotations

import asyncio
import html as _html
from collections import defaultdict
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ze.agents.registry import get_agent
from ze.agents.types import AgentContext, AgentResult
from ze.capability.types import GateDecision
from ze.errors import GoalExecutionError
from ze.goals.planner import GoalPlanner
from ze.goals.store import GoalStore
from ze.goals.types import (
    Goal,
    GoalLearning,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
)
from ze.logging import get_logger
from ze.proactive.notifier import ProactiveNotifier

log = get_logger(__name__)

_DONE_MILESTONE_STATUSES = frozenset({MilestoneStatus.COMPLETED, MilestoneStatus.SKIPPED})


class GoalExecutor:
    def __init__(
        self,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
        notifier: ProactiveNotifier,
    ) -> None:
        self._store = goal_store
        self._planner = goal_planner
        self._notifier = notifier
        self._advance_locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def advance(self, goal_id: UUID) -> None:
        """Advance execution of a goal by one step. Serialized per goal_id."""
        async with self._advance_locks[goal_id]:
            await self._advance_unlocked(goal_id)

    async def _advance_unlocked(self, goal_id: UUID) -> None:
        goal = await self._store.get_goal(goal_id)
        if goal is None or goal.status != GoalStatus.ACTIVE:
            return

        milestones = await self._store.list_milestones(goal_id)
        for stuck in [m for m in milestones if m.status == MilestoneStatus.IN_PROGRESS]:
            log.warning(
                "milestone_in_progress_reset",
                goal_id=str(goal_id),
                milestone_id=str(stuck.id),
                sequence=stuck.sequence,
            )
            await self._store.update_milestone(stuck.id, MilestoneStatus.PENDING)

        milestones = await self._store.list_milestones(goal_id)
        pending = [m for m in milestones if m.status == MilestoneStatus.PENDING]

        if not pending:
            await self._store.update_status(goal_id, GoalStatus.COMPLETED)
            await self._notifier.push(
                f"🏁 Goal <b>{_html.escape(goal.title)}</b> is complete!\n\n"
                f"<i>{_html.escape(goal.success_condition)}</i>",
                parse_mode="HTML",
            )
            log.info("goal_completed", goal_id=str(goal_id))
            return

        next_milestone = pending[0]

        # Check if there is a gate that fires before this milestone
        gate = await self._store.get_pending_gate(goal_id)
        if gate is not None and self._gate_should_fire(gate, next_milestone, milestones):
            completed = [m for m in milestones if m.status in _DONE_MILESTONE_STATUSES]
            await self._fire_gate(goal, gate, completed, pending)
            return

        # Execute the milestone
        await self._store.update_milestone(next_milestone.id, MilestoneStatus.IN_PROGRESS)
        log.info("milestone_started", goal_id=str(goal_id), sequence=next_milestone.sequence, title=next_milestone.title)

        try:
            output = await self._execute_milestone(next_milestone)
            await self._store.update_milestone(next_milestone.id, MilestoneStatus.COMPLETED, output=output)
            log.info("milestone_completed", goal_id=str(goal_id), sequence=next_milestone.sequence)
        except GoalExecutionError as exc:
            error_msg = str(exc)
            log.warning("milestone_failed", goal_id=str(goal_id), sequence=next_milestone.sequence, error=error_msg)
            await self._store.update_milestone(next_milestone.id, MilestoneStatus.SKIPPED, output=f"Failed: {error_msg}")
            await self._store.add_learning(GoalLearning(
                goal_id=goal_id,
                content=f"Milestone {next_milestone.sequence} ({next_milestone.title}) failed: {error_msg}",
                source="milestone_completion",
            ))
            await self._notifier.push(
                f"⚠️ Milestone <b>{_html.escape(next_milestone.title)}</b> failed.\n"
                f"<code>{_html.escape(error_msg[:200])}</code>\n\n"
                f"Continuing to next step. You can redirect this goal if needed.",
                parse_mode="HTML",
            )
            # Continue to next milestone
            asyncio.create_task(self.advance(goal_id))
            return

        # Extract learning
        try:
            learning_text = await self._planner.extract_learning(next_milestone.title, output)
            await self._store.add_learning(GoalLearning(
                goal_id=goal_id,
                content=learning_text,
                source="milestone_completion",
            ))
            await self._store.append_learnings(goal_id, learning_text)
        except Exception as exc:
            log.warning("learning_extraction_failed", error=str(exc))

        # Progress notification
        total = len(milestones)
        completed_count = sum(1 for m in milestones if m.status == MilestoneStatus.COMPLETED) + 1
        await self._notifier.push(
            f"✅ <b>{_html.escape(next_milestone.title)}</b> done ({completed_count}/{total}).",
            parse_mode="HTML",
        )

        # Continue loop
        asyncio.create_task(self.advance(goal_id))

    async def approve_plan(self, goal_id: UUID) -> bool:
        """Activate a goal after the user approves its plan. Returns False if not planning."""
        goal = await self._store.get_goal(goal_id)
        if goal is None or goal.status != GoalStatus.PLANNING:
            return False
        await self._store.update_status(goal_id, GoalStatus.ACTIVE)
        log.info("goal_plan_approved", goal_id=str(goal_id))
        asyncio.create_task(self.advance(goal_id))
        return True

    async def reject_plan(self, goal_id: UUID) -> bool:
        """Abandon a goal when the user rejects its plan."""
        goal = await self._store.get_goal(goal_id)
        if goal is None or goal.status != GoalStatus.PLANNING:
            return False
        await self._store.update_status(goal_id, GoalStatus.ABANDONED)
        log.info("goal_plan_rejected", goal_id=str(goal_id))
        return True

    async def handle_gate_approved(self, gate_id: UUID) -> None:
        gate = await self._store.get_gate(gate_id)
        if gate is None or gate.status != GateStatus.AWAITING_APPROVAL:
            return
        await self._store.resolve_gate(gate_id, GateStatus.APPROVED)
        await self._store.update_status(gate.goal_id, GoalStatus.ACTIVE)
        log.info("gate_approved", gate_id=str(gate_id), goal_id=str(gate.goal_id))
        asyncio.create_task(self.advance(gate.goal_id))

    async def handle_gate_stopped(self, gate_id: UUID) -> None:
        gate = await self._store.get_gate(gate_id)
        if gate is None or gate.status != GateStatus.AWAITING_APPROVAL:
            return
        await self._store.resolve_gate(gate_id, GateStatus.STOPPED)
        await self._store.update_status(gate.goal_id, GoalStatus.ABANDONED)
        goal = await self._store.get_goal(gate.goal_id)
        title = goal.title if goal else str(gate.goal_id)
        await self._notifier.push(
            f"🛑 Goal <b>{_html.escape(title)}</b> stopped.",
            parse_mode="HTML",
        )
        log.info("gate_stopped", gate_id=str(gate_id), goal_id=str(gate.goal_id))

    async def handle_gate_redirected(self, gate_id: UUID, feedback: str) -> None:
        gate = await self._store.get_gate(gate_id)
        if gate is None or gate.status != GateStatus.AWAITING_APPROVAL:
            return

        goal = await self._store.get_goal(gate.goal_id)
        if goal is None:
            return

        await self._store.add_learning(GoalLearning(
            goal_id=gate.goal_id,
            content=f"User redirect at checkpoint '{gate.title}': {feedback}",
            source="gate_feedback",
        ))
        await self._store.append_learnings(gate.goal_id, f"User redirect: {feedback}")

        # Get completed milestones to inform replanning
        milestones = await self._store.list_milestones(gate.goal_id)
        completed = [m for m in milestones if m.status == MilestoneStatus.COMPLETED]
        next_seq = max((m.sequence for m in completed), default=0) + 1

        try:
            new_milestones, new_gates = await self._planner.replan_remaining(
                goal, completed, feedback, next_seq
            )
        except Exception as exc:
            log.warning("replan_failed", error=str(exc))
            await self._notifier.push(
                f"⚠️ Could not replan goal: {_html.escape(str(exc))}",
                parse_mode="HTML",
            )
            return

        # Fix goal_id on new items (planner uses sentinel)
        for m in new_milestones:
            m.goal_id = gate.goal_id
        for g in new_gates:
            g.goal_id = gate.goal_id

        await self._store.replace_pending_milestones(gate.goal_id, new_milestones)
        await self._store.replace_pending_gates(gate.goal_id, new_gates)

        await self._store.resolve_gate(gate_id, GateStatus.REDIRECTED, user_feedback=feedback)
        await self._store.update_status(gate.goal_id, GoalStatus.ACTIVE)
        log.info("gate_redirected", gate_id=str(gate_id), goal_id=str(gate.goal_id))
        asyncio.create_task(self.advance(gate.goal_id))

    # ── Private ────────────────────────────────────────────────────────────────

    @staticmethod
    def _gate_should_fire(
        gate,
        next_milestone: Milestone,
        milestones: list[Milestone],
    ) -> bool:
        """True when the prior milestone is done and this gate blocks the next step."""
        if gate.status != GateStatus.PENDING:
            return False
        if gate.after_sequence != next_milestone.sequence - 1:
            return False
        prior = [m for m in milestones if m.sequence == gate.after_sequence]
        if not prior:
            return False
        return prior[0].status in _DONE_MILESTONE_STATUSES

    async def _execute_milestone(self, milestone: Milestone) -> str:
        agent_name = milestone.agent_hint or "companion"
        try:
            agent = get_agent(agent_name)
        except Exception:
            agent = get_agent("companion")

        ctx = AgentContext(
            session_id=f"goal:{milestone.goal_id}",
            prompt=milestone.description,
            intent=milestone.intent,
            gate_decision=GateDecision.EXECUTE,
        )

        try:
            result: AgentResult = await agent.run(ctx)
        except GoalExecutionError:
            raise
        except Exception as exc:
            raise GoalExecutionError(
                f"Milestone {milestone.sequence} ({milestone.title}) failed: {exc}"
            ) from exc
        return result.response

    async def _fire_gate(
        self,
        goal: Goal,
        gate,
        completed: list[Milestone],
        pending: list[Milestone],
    ) -> None:
        context_lines = [f"• {m.title}: {m.output[:150]}" for m in completed] or ["• No milestones completed yet."]
        plan_lines = [f"• {m.title}" for m in pending[:5]]

        context_summary = "\n".join(context_lines)
        plan_summary = "\n".join(plan_lines)

        await self._store.fire_gate(gate.id, context_summary, plan_summary)
        await self._store.update_status(goal.id, GoalStatus.AWAITING_GATE)

        text = (
            f"🎯 <b>{_html.escape(goal.title)}</b> — checkpoint\n\n"
            f"<b>What Ze has done:</b>\n{_html.escape(context_summary)}\n\n"
            f"<b>What Ze plans next:</b>\n{_html.escape(plan_summary)}\n\n"
            "Approve to continue, or send new instructions."
        )

        gate_id_str = str(gate.id)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Proceed", callback_data=f"goal:approve:{gate_id_str}"),
            InlineKeyboardButton(text="🛑 Stop", callback_data=f"goal:stop:{gate_id_str}"),
            InlineKeyboardButton(text="✏️ Redirect", callback_data=f"goal:redirect:{gate_id_str}"),
        ]])

        await self._notifier.push_with_keyboard(text, keyboard, parse_mode="HTML")
        log.info("gate_fired", gate_id=str(gate.id), goal_id=str(goal.id))
