from __future__ import annotations

import html as _html
import json
from typing import AsyncIterator
from uuid import UUID

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.errors import GoalPlanError
from ze.goals.planner import GoalPlanner
from ze.goals.store import GoalStore
from ze.goals.types import Goal, GoalStatus, MilestoneStatus
from ze.openrouter.client import OpenRouterClient
from ze.proactive.notifier import ProactiveNotifier
from ze.settings import Settings
from ze.telegram.keyboards import goal_plan_confirmation_keyboard

_AGENT_INSTRUCTIONS = """\
You are Ze's goal manager. You create, inspect, pause, resume, and abandon long-running goals.

A goal is a multi-week objective Ze executes autonomously, pausing at verification gates for
human approval before continuing.

Parse the user's intent and extract the relevant parameters. Respond with a JSON object:
{
  "action": "create" | "status" | "list" | "pause" | "resume" | "abandon",
  "goal_id": "<uuid or null>",
  "title": "<title for create or null>",
  "objective": "<what the user wants to achieve or null>",
  "success_condition": "<what done looks like or null>",
  "time_horizon": "<e.g. '6 weeks', 'by end of June' or null>",
  "type": "custom | outreach | research"
}

Respond ONLY with the JSON object — no explanation.\
"""


@register
class GoalAgent(BaseAgent):
    name = "goals"
    tools: list[str] = []

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
        notifier: ProactiveNotifier,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._store = goal_store
        self._planner = goal_planner
        self._notifier = notifier

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "goals.managing")
        raw = await self._client.complete(
            messages=[{"role": "user", "content": ctx.prompt}],
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return AgentResult(
                agent=self.name,
                response="I couldn't understand that goal request. Try: 'create a goal', 'list my goals', 'goal status'.",
            )

        action = parsed.get("action", "list")
        goal_id_str = parsed.get("goal_id")
        goal_id = UUID(goal_id_str) if goal_id_str else None

        match action:
            case "create":
                response = await self._handle_create(parsed)
            case "status":
                response = await self._handle_status(goal_id)
            case "list":
                response = await self._handle_list()
            case "pause":
                response = await self._handle_set_status(goal_id, GoalStatus.PAUSED, "paused")
            case "resume":
                response = await self._handle_resume(goal_id)
            case "abandon":
                response = await self._handle_set_status(goal_id, GoalStatus.ABANDONED, "abandoned")
            case _:
                response = "Unknown goal action."

        return AgentResult(agent=self.name, response=response)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_create(self, parsed: dict) -> str:
        title = parsed.get("title")
        objective = parsed.get("objective")
        success_condition = parsed.get("success_condition")

        if not title or not objective or not success_condition:
            return "Please provide a title, objective, and success condition to create a goal."

        goal = Goal(
            title=title,
            objective=objective,
            success_condition=success_condition,
            time_horizon=parsed.get("time_horizon") or "",
            type=parsed.get("type") or "custom",
            status=GoalStatus.PLANNING,
        )

        try:
            milestones, gates = await self._planner.plan(goal)
        except GoalPlanError as exc:
            return f"Couldn't plan the goal: {exc}"

        goal = await self._store.create_goal(goal)

        for m in milestones:
            m.goal_id = goal.id
        for g in gates:
            g.goal_id = goal.id

        for m in milestones:
            await self._store.create_milestone(m)
        for g in gates:
            await self._store.create_gate(g)

        step_summary = "\n".join(f"  {m.sequence}. {m.title}" for m in milestones)
        gate_summary = "\n".join(
            f"  Gate after step {g.after_sequence}: {g.title}" for g in gates
        ) or "  (none)"

        plan_text = (
            f"🎯 <b>{_html.escape(title)}</b> — proposed plan\n\n"
            f"<b>Milestones:</b>\n{_html.escape(step_summary)}\n\n"
            f"<b>Checkpoints:</b>\n{_html.escape(gate_summary)}\n\n"
            "Start this goal?"
        )
        await self._notifier.push_with_keyboard(
            plan_text,
            goal_plan_confirmation_keyboard(goal.id),
            parse_mode="HTML",
        )

        return (
            f"Goal **{title}** planned ({len(milestones)} milestones). "
            f"Approve in Telegram to start, or cancel to discard."
        )

    async def _handle_status(self, goal_id: UUID | None) -> str:
        if not goal_id:
            # Try the most recent active goal
            active = await self._store.list_active()
            if not active:
                return "No active goals. Create one with 'create a goal to...'."
            goal_id = active[0].id

        goal = await self._store.get_goal(goal_id)
        if not goal:
            return f"Goal not found: {goal_id}"

        milestones = await self._store.list_milestones(goal_id)
        learnings = await self._store.list_learnings(goal_id)
        gate = await self._store.get_pending_gate(goal_id)

        completed = sum(1 for m in milestones if m.status == MilestoneStatus.COMPLETED)
        skipped = sum(1 for m in milestones if m.status.value == "skipped")
        total = len(milestones)

        lines = [
            f"**{goal.title}**",
            f"Status: {goal.status.value}",
            f"Progress: {completed}/{total} milestones done" + (f" ({skipped} skipped)" if skipped else ""),
            "",
        ]

        if gate:
            lines.append(f"⏸ Paused at checkpoint: *{gate.title}*")
            lines.append("")

        if goal.learnings:
            lines.append(f"**Learnings:**\n{goal.learnings[:500]}")

        return "\n".join(lines)

    async def _handle_list(self) -> str:
        goals = await self._store.list_all()
        if not goals:
            return "No goals yet. Start one by describing what you want to achieve."
        lines = []
        for g in goals:
            lines.append(f"- **{g.title}** ({g.status.value}) — {g.objective[:80]}")
            if len(g.objective) > 80:
                lines[-1] += "…"
        return "Goals:\n" + "\n".join(lines)

    async def _handle_set_status(
        self, goal_id: UUID | None, status: GoalStatus, verb: str
    ) -> str:
        if not goal_id:
            return f"Please specify a goal ID to {verb}."
        goal = await self._store.get_goal(goal_id)
        if not goal:
            return f"Goal not found: {goal_id}"
        await self._store.update_status(goal_id, status)
        return f"Goal **{goal.title}** {verb}."

    async def _handle_resume(self, goal_id: UUID | None) -> str:
        if not goal_id:
            return "Please specify a goal ID to resume."
        goal = await self._store.get_goal(goal_id)
        if not goal:
            return f"Goal not found: {goal_id}"
        if goal.status != GoalStatus.PAUSED:
            return f"Goal **{goal.title}** is not paused (status: {goal.status.value})."
        await self._store.update_status(goal_id, GoalStatus.ACTIVE)
        asyncio.create_task(self._executor.advance(goal_id))
        return f"Goal **{goal.title}** resumed."
