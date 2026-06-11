from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from ze_core import defaults
from ze_core.errors import GoalPlanError
from typing import Any
from ze_memory.types import Episode, Fact, Procedure, RetrievalRequest
from ze_personal.goals.types import (
    Goal,
    GateStatus,
    GoalLearning,
    GoalStatus,
    GoalSuggestion,
    Milestone,
    MilestoneStatus,
    PriorMilestoneOutput,
    SuggestionStatus,
    VerificationGate,
)
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
      "sequence": 1,
      "reuse_hint": ""
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
  reason, summarise, or plan → "reason"

When a PRIOR WORK FROM OTHER GOALS section is present:
- If a prior milestone's output is directly relevant to a planned milestone (same research
  domain, same data source, same type of document), set "reuse_hint" on that milestone.
- Hint format: "Prior goal '[title]' already produced [brief description] ([N] days ago).
  Retrieve trace before re-running — reuse if still current."
- If the prior work is likely stale for this domain (job listings, company headcounts,
  market prices), add: "Note: may be outdated."
- Only set reuse_hint when there is clear, specific overlap. Do not force hints for vague
  thematic similarity.
- If nothing is reusable, omit reuse_hint or set it to null.\
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

_SUGGESTION_SYSTEM = """\
You are analysing a user's memory, past goals, and retrospectives to identify one specific,
high-value goal they haven't yet set.

CONSTRAINTS:
- You must cite a concrete source: a specific retrospective, a cluster of related facts, or a
  repeated theme across multiple episodes. Vague observations ("the user seems interested in…")
  are not acceptable.
- The proposed goal must not duplicate any active goal listed below.
- If you cannot identify a clear, grounded opportunity, respond with {"suggestion": null}.

Respond ONLY in JSON — no explanation, no markdown:
{
  "suggestion": {
    "title": "...",
    "objective": "...",
    "rationale": "...",
    "source_type": "retrospective" | "memory_facts" | "weekly_narrative",
    "source_ref": "..."
  } | null
}\
"""

_PROMOTION_SYSTEM = """\
You are extracting generalizable user facts from the learnings of a completed goal.

A generalizable fact is something true about the USER — their preferences, habits,
strategies, decision-making patterns — that applies beyond this specific goal and
would be useful context for future tasks.

A goal-specific learning is NOT a generalizable fact:
  - research about a third-party company, product, or person
  - factual findings about the external world
  - contact details or relationship data
  - anything that is only relevant to this goal's subject matter

Rules:
1. Only extract facts that generalise — user preferences, communication style,
   decision patterns, domain strategies that reflect how the user works.
2. Every fact must be a statement about the USER, not about a third party or the
   external world. The subject of each value must be the user ("prefers...",
   "tends to...", "works best when..."). If the subject is not the user, omit it.
3. Each fact must be written as a short, atomic key-value pair.
4. Produce at most 5 facts. If fewer than 1 generalizable fact exists, return an empty list.
5. Do not fabricate or over-interpret. If a learning is ambiguous, omit it.

Return JSON:
{
  "facts": [
    {"key": "...", "value": "..."},
    ...
  ]
}
If nothing is promotable, return: {"facts": []}\
"""

_PROCEDURE_SYSTEM = """\
You are extracting a reusable procedure from a completed goal execution.

A procedure captures HOW the goal was accomplished — the generalizable sequence of steps
that could be reused for a similar goal in the future. Focus on the method, not the
specific subject matter.

Return JSON:
{
  "name": "short verb-phrase name for the procedure",
  "trigger": "when would this procedure be useful? (one sentence)",
  "preconditions": ["what must be true before starting?"],
  "steps": ["step 1", "step 2", ...],
  "success_criteria": ["how do you know it worked?"]
}

If the goal was too specific or opportunistic to generalise into a reusable procedure,
return: {"name": null}\
"""

_PROPER_NOUN_RE = re.compile(r"[A-Z][a-z]+|\d{4}|\bQ[1-4]\b")


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
                reuse_hint=(item.get("reuse_hint") or "")[:300],
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
        memory_store: Any = None,
    ) -> None:
        self._client = client
        self._model = model
        self._memory = memory_store

    async def plan(
        self,
        goal: Goal,
        prior_work: list[PriorMilestoneOutput] | None = None,
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
        procedures = await self._fetch_procedures(goal.title)
        if procedures:
            lines = [
                f"  - [{p.name}] {p.trigger}\n    Steps: {'; '.join(p.steps[:3])}"
                for p in procedures
            ]
            prompt += "\n\nREUSABLE PROCEDURES FROM PAST GOALS:\n" + "\n".join(lines)
        if prior_work:
            lines = [
                f"  - \"{p.goal_title}\" → \"{p.milestone_title}\" "
                f"({p.completed_days_ago}d ago): {p.output_snippet}"
                for p in prior_work
            ]
            prompt += "\n\nPRIOR WORK FROM OTHER GOALS:\n" + "\n".join(lines)

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
        prior_work: list[PriorMilestoneOutput] | None = None,
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
        if prior_work:
            lines = [
                f"  - \"{p.goal_title}\" → \"{p.milestone_title}\" "
                f"({p.completed_days_ago}d ago): {p.output_snippet}"
                for p in prior_work
            ]
            prompt += "\n\nPRIOR WORK FROM OTHER GOALS:\n" + "\n".join(lines)

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

    async def promote_learnings(
        self,
        goal: Goal,
        learnings: list[GoalLearning],
    ) -> list[Fact]:
        """Extract generalizable user facts from goal learnings. Returns [] on any error."""
        learnings_text = "\n".join(
            f"  - [{l.source}] {l.content}" for l in learnings
        )
        prompt = (
            f"Goal: {goal.title}\n"
            f"Objective: {goal.objective}\n\n"
            f"Learnings from this goal:\n{learnings_text}"
        )
        raw = await self._client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=self._model,
            system=_PROMOTION_SYSTEM,
        )
        try:
            data = json.loads(raw)
            return [
                Fact(
                    id=None,
                    subject_id=None,
                    predicate=f["key"],
                    object_text=None,
                    object_id=None,
                    value=f["value"],
                    reviewed=False,
                )
                for f in data.get("facts", [])
                if isinstance(f.get("key"), str) and isinstance(f.get("value"), str)
            ][:5]
        except Exception:
            return []

    async def extract_procedure(
        self,
        goal: Goal,
        milestones: list[Milestone],
    ) -> Procedure | None:
        """Derive a reusable procedure from a completed goal. Returns None if not generalisable."""
        completed = [m for m in milestones if m.status == MilestoneStatus.COMPLETED]
        if not completed:
            return None
        steps = [f"{m.sequence}. {m.title}" for m in completed]
        prompt = (
            f"Goal: {goal.title}\n"
            f"Objective: {goal.objective}\n\n"
            f"Completed milestones:\n" + "\n".join(steps)
        )
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                system=_PROCEDURE_SYSTEM,
            )
            data = json.loads(raw)
            if not data.get("name"):
                return None
            return Procedure(
                id=None,
                name=data["name"],
                trigger=data.get("trigger", ""),
                preconditions=data.get("preconditions", []),
                steps=data.get("steps", [step.split(". ", 1)[-1] for step in steps]),
                success_criteria=data.get("success_criteria", []),
            )
        except Exception as exc:
            log.warning("goal_procedure_extraction_failed", goal_id=str(goal.id), error=str(exc))
            return None

    async def _fetch_procedures(self, query: str) -> list[Procedure]:
        if self._memory is None:
            return []
        try:
            from ze_core.embeddings import get_embedder
            embedding = get_embedder().encode(query)
            request = RetrievalRequest(
                module="planner",
                agent="planner",
                query_text=query,
                query_embedding=embedding,
            )
            ctx = await self._memory.retrieve(request)
            return ctx.procedures
        except Exception as exc:
            log.warning("planner_procedure_fetch_failed", error=str(exc))
            return []

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

    async def generate_suggestion(
        self,
        memory_facts: list[Fact],
        episodes: list[Episode],
        retrospectives: list[Goal],
        active_goal_titles: list[str],
    ) -> GoalSuggestion | None:
        """
        Synthesise signal into a goal suggestion. Returns None if signal is insufficient
        or the confidence gate rejects the LLM output.
        """
        facts_text = "\n".join(f"  - [{f.predicate}] {f.value}" for f in memory_facts) or "  (none)"
        episodes_text = "\n".join(
            f"  - [{e.created_at.strftime('%Y-%m-%d') if e.created_at else '?'}] "
            f"{(e.summary or e.response[:200])}"
            for e in episodes
        ) or "  (none)"
        retros_text = "\n".join(
            f"  - Goal '{g.title}': {(g.retrospective_text or '')[:400]}"
            for g in retrospectives
            if g.retrospective_text
        ) or "  (none)"
        active_text = "\n".join(f"  - {t}" for t in active_goal_titles) or "  (none)"

        prompt = (
            f"ACTIVE GOALS (do not duplicate):\n{active_text}\n\n"
            f"RECENT SIGNAL:\n"
            f"Retrospectives (last 60 days):\n{retros_text}\n\n"
            f"Memory facts (last 90 days, highest-confidence):\n{facts_text}\n\n"
            f"Recent episodes (last 30 days):\n{episodes_text}"
        )

        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                system=_SUGGESTION_SYSTEM,
            )
            data = json.loads(raw)
            s = data.get("suggestion")
            if not s:
                return None

            title = s["title"]
            objective = s["objective"]
            rationale = s["rationale"]
            source_type = s["source_type"]
            source_ref = s["source_ref"]
        except Exception as exc:
            log.warning("goal_suggestion_llm_failed", error=str(exc))
            return None

        # Confidence gate
        if len(rationale.split()) < 15:
            log.info("goal_suggestion_gate_rejected", reason="rationale_too_short")
            return None
        if not _PROPER_NOUN_RE.search(rationale):
            log.info("goal_suggestion_gate_rejected", reason="rationale_generic")
            return None
        if len(objective.split()) < 10:
            log.info("goal_suggestion_gate_rejected", reason="objective_too_short")
            return None
        title_lower = title.lower()
        if any(title_lower in t.lower() or t.lower() in title_lower for t in active_goal_titles):
            log.info("goal_suggestion_gate_rejected", reason="duplicates_active_goal")
            return None

        return GoalSuggestion(
            id=uuid4(),
            title=title,
            objective=objective,
            rationale=rationale,
            source_type=source_type,
            source_ref=source_ref,
            status=SuggestionStatus.PENDING,
            suggested_at=datetime.now(timezone.utc),
        )

    def create_goal_from_suggestion(self, suggestion: GoalSuggestion) -> Goal:
        """Pure mapping — no LLM call. Maps suggestion fields into an active Goal."""
        return Goal(
            title=suggestion.title,
            objective=suggestion.objective,
            success_condition=suggestion.objective,
            status=GoalStatus.ACTIVE,
            type="suggested",
        )
