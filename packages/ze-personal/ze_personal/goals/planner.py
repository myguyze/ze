from __future__ import annotations

import json
from uuid import UUID

from ze_core import defaults
from ze_core.errors import GoalPlanError
from ze_personal.goals.types import Goal, GateStatus, GoalLearning, Milestone, MilestoneStatus, VerificationGate
from ze_core.logging import get_logger
from ze_core.openrouter.client import OpenRouterClient

log = get_logger(__name__)

_PLAN_SYSTEM = """\
You decompose a multi-week goal into an ordered list of milestones and verification gates.

A milestone is a concrete unit of work — something an agent can execute in a single run.
A gate is a pause point where the application shows its progress and waits for human approval before continuing.

Output ONLY a JSON object with two keys — no explanation, no markdown:
{
  "milestones": [
    {
      "title": "Short action title",
      "description": "Detailed task instruction for the agent",
      "agent_hint": "research | companion | null",
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
- Place a gate after any milestone that produces irreversible output.
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


_RETROSPECTIVE_SYSTEM = """\
You write a concise retrospective for a completed goal. Cover three things:
1. What was accomplished (be specific — reference actual outputs, not just milestone titles).
2. Key learnings or insights surfaced during execution.
3. Suggested next steps or follow-on goals, if any.

Write in plain language, 3-5 short paragraphs. No headers. Address the user directly.\
"""

_WEEKLY_NARRATIVE_SYSTEM = """\
You write one paragraph summarizing progress on a goal over the past week.
Be specific about what was accomplished. If there's a pending gate, call it out.
Mention what comes next. Write in plain language, 3-5 sentences maximum.\
"""

_GATE_NARRATIVE_SYSTEM = """\
You summarize completed work at a goal checkpoint. Be concise and specific.
Write 2-4 sentences covering: what was accomplished, any notable findings or blockers,
and why this is a natural pause point. Write in plain language as if briefing the goal owner.
Output only the narrative — no headers, no bullet points.\
"""

_SENTINEL_GOAL_ID = UUID("00000000-0000-0000-0000-000000000000")


def _parse_plan(raw: str, goal_id: UUID) -> tuple[list[Milestone], list[VerificationGate]]:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")

        raw_milestones = data.get("milestones", [])
        if not raw_milestones:
            raise ValueError("No milestones in plan")

        milestones = [
            Milestone(
                goal_id=goal_id,
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
                goal_id=goal_id,
                after_sequence=g["after_sequence"],
                title=g["title"],
                status=GateStatus.PENDING,
            )
            for g in data.get("gates", [])
        ]
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("goal_plan_parse_error", error=str(exc), raw=raw[:200])
        raise GoalPlanError(f"Planner returned invalid plan: {exc}") from exc

    return milestones, gates


class GoalPlanner:
    def __init__(
        self,
        client: OpenRouterClient,
        model: str = defaults.MODEL_GOAL_PLAN,
    ) -> None:
        self._client = client
        self._model = model

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
            model=self._model,
            system=_PLAN_SYSTEM,
        )

        milestones, gates = _parse_plan(raw, _SENTINEL_GOAL_ID)
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
            model=self._model,
            system=_PLAN_SYSTEM,
        )

        milestones, gates = _parse_plan(raw, _SENTINEL_GOAL_ID)
        milestones, gates = _normalize_and_validate(
            milestones, gates, min_sequence=next_sequence,
        )
        return milestones, gates

    async def synthesize_retrospective(
        self,
        goal: Goal,
        milestones: list[Milestone],
        learnings: list[GoalLearning],
    ) -> str:
        """Produce a goal completion retrospective."""
        milestone_lines = "\n".join(
            f"  {m.sequence}. {m.title}: {(m.output or '')[:300]}"
            for m in milestones
        ) or "  (none)"
        learnings_text = "\n".join(
            f"  - {l.content}" for l in learnings[-5:]
        ) or "  (none)"
        prompt = (
            f"Goal: {goal.title}\n"
            f"Objective: {goal.objective}\n"
            f"Success condition: {goal.success_condition}\n\n"
            f"Completed milestones:\n{milestone_lines}\n\n"
            f"Key learnings:\n{learnings_text}"
        )
        return await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            system=_RETROSPECTIVE_SYSTEM,
        )

    async def synthesize_weekly_narrative(
        self,
        goal: Goal,
        completed_this_week: list[Milestone],
        pending_gate: VerificationGate | None,
        next_milestones: list[Milestone],
    ) -> str:
        """One paragraph: what Ze did this week on this goal, and what comes next."""
        completed_text = "\n".join(
            f"  - {m.title}: {(m.output or '')[:200]}"
            for m in completed_this_week
        ) or "  (none this week)"
        gate_text = f"\nAwaiting gate: {pending_gate.title}" if pending_gate else ""
        next_text = "\n".join(f"  - {m.title}" for m in next_milestones[:3]) or "  (none)"
        prompt = (
            f"Goal: {goal.title}\n"
            f"Objective: {goal.objective}\n\n"
            f"Completed this week:\n{completed_text}"
            f"{gate_text}\n\n"
            f"Coming next:\n{next_text}"
        )
        return await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            system=_WEEKLY_NARRATIVE_SYSTEM,
        )

    async def synthesize_gate_narrative(
        self,
        goal: Goal,
        completed: list[Milestone],
        gate_title: str,
    ) -> str:
        """Synthesize a 2-4 sentence narrative for a gate notification."""
        milestone_lines = "\n".join(
            f"  {m.sequence}. {m.title}: {(m.output or '')[:300]}"
            for m in completed
        ) or "  (none)"
        prompt = (
            f"Goal: {goal.title}\n"
            f"Success condition: {goal.success_condition}\n"
            f"Checkpoint: {gate_title}\n\n"
            f"Completed milestones:\n{milestone_lines}"
        )
        return await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            system=_GATE_NARRATIVE_SYSTEM,
        )

    async def extract_learning(self, milestone_title: str, output: str) -> str:
        """Extract a one-sentence learning from milestone output."""
        prompt = (
            f"Milestone: {milestone_title}\n"
            f"Output summary: {output[:500]}\n\n"
            "Write one concise sentence capturing the key insight or result from this milestone."
        )
        return await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            system="You extract one-sentence learnings from task outputs. Output only the sentence — no quotes, no explanation.",
        )
