from __future__ import annotations

import json

from ze_core import defaults
from ze_core.errors import WorkflowPlanError
from ze_core.logging import get_logger
from ze_core.openrouter.client import OpenRouterClient
from ze_memory.types import Procedure
from ze_personal.workflow.types import StepResult, WorkflowStep

log = get_logger(__name__)

_PLAN_SYSTEM = """\
You decompose a workflow description into an ordered list of steps.
Each step must have:
  "task"       — natural language instruction for the agent
  "agent_hint" — one of: research, calendar, email, companion (or null)
  "intent"     — one of: read, create, update, delete, execute, reason
  "verify"     — natural language criterion to check the step output (or null)

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


class WorkflowPlanner:
    def __init__(self, openrouter_client: OpenRouterClient) -> None:
        self._client = openrouter_client

    async def plan(self, description: str) -> list[WorkflowStep]:
        raw = await self._client.complete(
            messages=[{"role": "user", "content": description}],
            model=defaults.MODEL_WORKFLOW_PLAN,
            system=_PLAN_SYSTEM,
        )
        try:
            data = json.loads(raw)
            if not isinstance(data, list) or len(data) == 0:
                raise ValueError("Expected a non-empty JSON array")
            steps = [
                WorkflowStep(
                    task=item["task"],
                    agent_hint=item.get("agent_hint"),
                    verify=item.get("verify"),
                    intent=item.get("intent", "execute"),
                )
                for item in data
            ]
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning("workflow_plan_parse_error", error=str(exc), raw=raw[:200])
            raise WorkflowPlanError(f"Planner returned invalid plan: {exc}") from exc

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
            data = json.loads(raw)
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
            log.warning("workflow_procedure_extraction_failed", workflow=name, error=str(exc))
            return None

    async def extract_schedule(self, description: str) -> str | None:
        raw = await self._client.complete(
            messages=[{"role": "user", "content": description}],
            model=defaults.MODEL_WORKFLOW_PLAN,
            system=_SCHEDULE_SYSTEM,
        )
        try:
            data = json.loads(raw)
            return data.get("cron")
        except (json.JSONDecodeError, KeyError) as exc:
            log.warning("workflow_schedule_parse_error", error=str(exc), raw=raw[:200])
            raise WorkflowPlanError(f"Could not parse schedule: {exc}") from exc
