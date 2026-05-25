from __future__ import annotations

import json
from uuid import UUID

from ze.errors import GoalPlanError
from ze.goals.types import Goal, GateStatus, Milestone, MilestoneStatus, VerificationGate
from ze.logging import get_logger
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings

log = get_logger(__name__)


def _normalize_and_validate(
    milestones: list[Milestone],
    gates: list[VerificationGate],
    *,
    min_sequence: int = 1,
    require_gates: bool = True,
) -> tuple[list[Milestone], list[VerificationGate]]:
    if not milestones:
        raise GoalPlanError("No milestones in plan")
    if require_gates and not gates:
        raise GoalPlanError("Plan must include at least one verification gate")

    base = min(m.sequence for m in milestones)
    offset = min_sequence - base
    if offset:
        for m in milestones:
            m.sequence += offset
        for g in gates:
            g.after_sequence += offset

    milestones.sort(key=lambda m: m.sequence)
    gates.sort(key=lambda g: g.after_sequence)
    return milestones, gates


_PLAN_SYSTEM = """\
You decompose a multi-week goal into an ordered list of milestones and verification gates.

A milestone is a concrete unit of work — something Ze can execute in a single run.
A gate is a pause point where Ze shows its progress and waits for human approval before continuing.

Output ONLY a JSON object with two keys — no explanation, no markdown:
{
  "milestones": [
    {
      "title": "Short action title",
      "description": "Detailed task instruction for the agent",
      "agent_hint": "research | prospecting | email | calendar | companion | workflow | null",
      "intent": "read | create | update | delete | execute | reason",
      "sequence": 1
    }
  ],
  "gates": [
    {
      "after_sequence": 2,
      "title": "Short checkpoint title describing what the user is reviewing"
    }
  ]
}

Gate placement rules (apply ALL of them):
- Always place a gate before the first outreach or communication milestone.
- Place a gate after any milestone that produces irreversible output (sent emails, external posts, purchases).
- Place a gate at natural progress checkpoints — roughly every 3 milestones for goals with 6+ milestones.
- Include at minimum one gate, even for short goals.

Intent guidelines:
  retrieve information only → "read"
  create new items → "create"
  modify existing items → "update"
  remove items → "delete"
  run or trigger an external action → "execute"
  reason, summarise, or plan → "reason"\
"""


class GoalPlanner:
    def __init__(self, openrouter_client: OpenRouterClient, settings: Settings) -> None:
        self._client = openrouter_client
        self._settings = settings

    async def plan(
        self,
        goal: Goal,
    ) -> tuple[list[Milestone], list[VerificationGate]]:
        """Decompose a goal into milestones and gates. Returns unsaved instances."""
        prompt = (
            f"Goal: {goal.title}\n"
            f"Objective: {goal.objective}\n"
            f"Success condition: {goal.success_condition}\n"
            f"Time horizon: {goal.time_horizon or 'not specified'}"
        )
        if goal.learnings:
            prompt += f"\nLearnings so far:\n{goal.learnings}"

        raw = await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._settings.workflow_plan_model,
            system=_PLAN_SYSTEM,
        )

        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")

            raw_milestones = data.get("milestones", [])
            if not raw_milestones:
                raise ValueError("No milestones in plan")

            # Use a sentinel goal_id — caller will set the real one after creation
            _sentinel = UUID("00000000-0000-0000-0000-000000000000")

            milestones = [
                Milestone(
                    goal_id=_sentinel,
                    title=item["title"],
                    description=item["description"],
                    sequence=item["sequence"],
                    agent_hint=item.get("agent_hint"),
                    intent=item.get("intent", "execute"),
                    status=MilestoneStatus.PENDING,
                )
                for item in raw_milestones
            ]

            gates = [
                VerificationGate(
                    goal_id=_sentinel,
                    after_sequence=g["after_sequence"],
                    title=g["title"],
                    status=GateStatus.PENDING,
                )
                for g in data.get("gates", [])
            ]

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning("goal_plan_parse_error", error=str(exc), raw=raw[:200])
            raise GoalPlanError(f"Planner returned invalid plan: {exc}") from exc

        milestones, gates = _normalize_and_validate(milestones, gates)
        log.info("goal_planned", milestones=len(milestones), gates=len(gates))
        return milestones, gates

    async def replan_remaining(
        self,
        goal: Goal,
        completed_milestones: list[Milestone],
        feedback: str,
        next_sequence: int,
    ) -> tuple[list[Milestone], list[VerificationGate]]:
        """Re-plan remaining milestones after a redirect gate, incorporating user feedback."""
        completed_summary = "\n".join(
            f"  {m.sequence}. {m.title}: {m.output[:200]}" for m in completed_milestones
        ) or "  None yet."

        prompt = (
            f"Goal: {goal.title}\n"
            f"Objective: {goal.objective}\n"
            f"Success condition: {goal.success_condition}\n"
            f"Time horizon: {goal.time_horizon or 'not specified'}\n\n"
            f"Completed work:\n{completed_summary}\n\n"
            f"User redirect instructions: {feedback}\n\n"
            f"Generate only the REMAINING milestones starting at sequence {next_sequence}."
        )

        raw = await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._settings.workflow_plan_model,
            system=_PLAN_SYSTEM,
        )

        try:
            data = json.loads(raw)
            _sentinel = UUID("00000000-0000-0000-0000-000000000000")
            milestones = [
                Milestone(
                    goal_id=_sentinel,
                    title=item["title"],
                    description=item["description"],
                    sequence=item["sequence"],
                    agent_hint=item.get("agent_hint"),
                    intent=item.get("intent", "execute"),
                    status=MilestoneStatus.PENDING,
                )
                for item in data.get("milestones", [])
            ]
            gates = [
                VerificationGate(
                    goal_id=_sentinel,
                    after_sequence=g["after_sequence"],
                    title=g["title"],
                    status=GateStatus.PENDING,
                )
                for g in data.get("gates", [])
            ]
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            raise GoalPlanError(f"Replan failed: {exc}") from exc

        milestones, gates = _normalize_and_validate(
            milestones, gates, min_sequence=next_sequence,
        )
        return milestones, gates

    async def extract_learning(self, milestone_title: str, output: str) -> str:
        """Extract a one-sentence learning from milestone output."""
        prompt = (
            f"Milestone: {milestone_title}\n"
            f"Output summary: {output[:500]}\n\n"
            "Write one concise sentence capturing the key insight or result from this milestone."
        )
        return await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._settings.workflow_plan_model,
            system="You extract one-sentence learnings from task outputs. Output only the sentence — no quotes, no explanation.",
        )
