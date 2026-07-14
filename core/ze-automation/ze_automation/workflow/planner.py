from __future__ import annotations

import json

from ze_agents import defaults
from ze_agents.errors import WorkflowPlanError
from ze_logging import get_logger
from ze_agents.client import LLMClient
from ze_sdk.memory import Procedure
from ze_automation.workflow.types import Branch, StepResult, WorkflowStep
from ze_automation.workflow.validation import validate_workflow_steps

log = get_logger(__name__)

_TERMINAL_TARGETS = {"END", "FAIL"}


def validate_step_targets(steps: list[WorkflowStep]) -> None:
    """Raise WorkflowPlanError if any Branch.to/default_next/on_failure target is invalid."""
    validate_workflow_steps(steps)


_PLAN_SYSTEM = """\
You decompose a workflow description into an ordered list of steps.
Each step must have:
  "task"       — natural language instruction for the agent
  "agent_hint" — one of: research, calendar, email, companion (or null)
  "intent"     — one of: read, create, update, delete, execute, reason
  "verify"     — natural language criterion to check the step output (or null)

When the description contains an explicit either/or or conditional outcome, you MAY
also include on the relevant step(s):
  "id"           — stable step id such as "s0", "s1", ... (unique within the plan)
  "branches"     — ordered list of {"condition": "...", "to": "..."} pairs where
                   "to" is another step's id or the terminal targets "END" / "FAIL"
  "default_next" — step id or "END" / "FAIL" to use when no branch matches
  "on_failure"   — one of "fail" (default), "continue", or "skip_to:<step_id>"

For monitoring or checking steps that may legitimately find nothing new, author verify
criteria that accept an empty or negative finding as success (e.g. "confirms the check
ran; no new items is valid"). Prefer "on_failure": "continue" for non-critical
monitoring/enrichment steps when failure should not abort the whole run.

For plain sequential workflows with no conditional language, omit id, branches, and
default_next entirely — the system assigns ids and runs steps in list order.

Output ONLY a JSON array — no explanation, no markdown:
[{"task": "...", "agent_hint": "research", "intent": "read", "verify": "..."}, ...]

Intent guidelines:
  research/companion tasks that only retrieve information → "read"
  tasks that create new items (emails, events, workflows) → "create"
  tasks that modify existing items → "update"
  tasks that remove items → "delete"
  tasks that run or trigger something → "execute"
  tasks that reason, summarise, or plan → "reason"

Omit agent_hint and verify if not applicable (use null).\
"""

_PROCEDURE_SYSTEM = """\
You are extracting a reusable procedure from a completed workflow execution.

A procedure captures HOW the workflow was accomplished — the generalizable sequence of
steps that could be reused for a similar workflow in the future. Focus on the method,
not the specific subject matter.

Return JSON:
{
  "name": "short verb-phrase name for the procedure",
  "trigger": "when would this procedure be useful? (one sentence)",
  "preconditions": ["what must be true before starting?"],
  "steps": ["step 1", "step 2", ...],
  "success_criteria": ["how do you know it worked?"]
}

If the workflow was too specific or one-off to generalise into a reusable procedure,
return: {"name": null}\
"""

_SCHEDULE_SYSTEM = """\
Extract a cron expression (5-field: min hour dom month dow) from a natural language
schedule description. If no recurring schedule is implied, return null for "cron".

Output ONLY a JSON object — no explanation, no markdown:
{"cron": "0 8 * * 1"}   -- or --   {"cron": null}\
"""


def _extract_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("["):
        start = text.find("[")
        end = text.rfind("]") + 1
        if end > start:
            return text[start:end]

    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text


def _parse_branches(raw: object) -> list[Branch]:
    if not isinstance(raw, list):
        return []
    branches: list[Branch] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        condition = item.get("condition")
        target = item.get("to")
        if isinstance(condition, str) and isinstance(target, str):
            branches.append(Branch(condition=condition, to=target))
    return branches


def _parse_step(item: dict, index: int) -> WorkflowStep:
    default_next = item.get("default_next")
    if default_next is not None and not isinstance(default_next, str):
        default_next = None
    step_id = item.get("id")
    if not isinstance(step_id, str) or not step_id:
        step_id = f"s{index}"
    on_failure = item.get("on_failure", "fail")
    if not isinstance(on_failure, str) or not on_failure:
        on_failure = "fail"
    return WorkflowStep(
        task=item["task"],
        agent_hint=item.get("agent_hint"),
        verify=item.get("verify"),
        intent=item.get("intent", "execute"),
        id=step_id,
        branches=_parse_branches(item.get("branches")),
        default_next=default_next,
        on_failure=on_failure,
    )


class WorkflowPlanner:
    def __init__(self, openrouter_client: LLMClient) -> None:
        self._client = openrouter_client

    async def plan(self, description: str) -> list[WorkflowStep]:
        raw = await self._client.complete(
            messages=[{"role": "user", "content": description}],
            model=defaults.MODEL_WORKFLOW_PLAN,
            system=_PLAN_SYSTEM,
        )
        try:
            data = json.loads(_extract_json(raw))
            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("Expected a non-empty JSON array")
            steps = [_parse_step(item, index) for index, item in enumerate(data)]
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning("workflow_plan_parse_error", error=str(exc), raw=raw[:200])
            raise WorkflowPlanError(f"Planner returned invalid plan: {exc}") from exc

        validate_workflow_steps(steps)
        log.info("workflow_planned", steps=len(steps))
        return steps

    async def extract_procedure(
        self,
        name: str,
        step_results: list[StepResult],
    ) -> Procedure | None:
        """Derive a reusable procedure from a completed workflow. Returns None if not generalisable."""
        completed = [r for r in step_results if r.success]
        if not completed:
            return None
        steps_text = "\n".join(f"{i + 1}. {r.task}" for i, r in enumerate(completed))
        prompt = f"Workflow: {name}\n\nCompleted steps:\n{steps_text}"
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=defaults.MODEL_WORKFLOW_PLAN,
                system=_PROCEDURE_SYSTEM,
            )
            data = json.loads(_extract_json(raw))
            if not data.get("name"):
                return None
            return Procedure(
                id=None,
                name=data["name"],
                trigger=data.get("trigger", ""),
                preconditions=data.get("preconditions", []),
                steps=data.get("steps", [r.task for r in completed]),
                success_criteria=data.get("success_criteria", []),
            )
        except Exception as exc:
            log.warning(
                "workflow_procedure_extraction_failed", workflow=name, error=str(exc)
            )
            return None

    async def extract_schedule(self, description: str) -> str | None:
        raw = await self._client.complete(
            messages=[{"role": "user", "content": description}],
            model=defaults.MODEL_WORKFLOW_PLAN,
            system=_SCHEDULE_SYSTEM,
        )
        try:
            data = json.loads(_extract_json(raw))
            return data.get("cron")
        except (json.JSONDecodeError, KeyError) as exc:
            log.warning("workflow_schedule_parse_error", error=str(exc), raw=raw[:200])
            raise WorkflowPlanError(f"Could not parse schedule: {exc}") from exc
