from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncIterator
from uuid import UUID

from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.capability.types import Mode
from ze_core.orchestration.types import AgentContext, AgentResult
from ze.errors import WorkflowPlanError
from ze_core.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.workflow.planner import WorkflowPlanner
from ze.workflow.scheduler import WorkflowScheduler
from ze.workflow.store import WorkflowStore
from ze.workflow.types import Workflow

_AGENT_INSTRUCTIONS = """\
You are Ze's workflow manager. You create, list, enable, disable, delete, and trigger
stored workflows. A workflow is a named sequence of tasks Ze executes in order, with
an optional recurring schedule.

Parse the user's intent and extract the relevant parameters. Respond with a JSON object:
{
  "action": "create" | "list" | "get" | "enable" | "disable" | "delete" | "trigger",
  "name": "<workflow name or null>",
  "description": "<description for create or null>",
  "schedule_description": "<schedule string e.g. 'every Monday at 8am' or null>"
}

Respond ONLY with the JSON object — no explanation.\
"""


@agent
class WorkflowManagerAgent(BaseAgent):
    name = "workflow"
    description = """
      Manages stored workflows and recurring scheduled tasks. Use when the user wants
      to create, list, enable, disable, delete, or manually run a named workflow or
      recurring automated task.
    """
    model = "anthropic/claude-sonnet-4-5"
    vision_capable = True
    timeout = 60
    tools: list[str] = []
    intent_map = {"read": "", "manage": ""}
    capabilities = {
        "read": Mode.AUTONOMOUS,
        "manage": Mode.CONFIRM,
    }

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        workflow_store: WorkflowStore,
        workflow_planner: WorkflowPlanner,
        workflow_scheduler: WorkflowScheduler,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._client = openrouter_client
        self._store = workflow_store
        self._planner = workflow_planner
        self._scheduler = workflow_scheduler

    async def run(self, ctx: AgentContext) -> AgentResult:
        key = "workflow.managing" if ctx.intent == "manage" else "workflow.reading"
        await self.emit(ctx, key)
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
                response="I couldn't understand that workflow request. Try: 'create a workflow', 'list workflows', 'trigger workflow X'.",
            )

        action = parsed.get("action", "list")
        name = parsed.get("name")
        description = parsed.get("description")
        schedule_description = parsed.get("schedule_description")

        match action:
            case "create":
                response = await self._handle_create(name, description, schedule_description)
            case "list":
                response = await self._handle_list()
            case "get":
                response = await self._handle_get(name)
            case "enable":
                response = await self._handle_set_enabled(name, True)
            case "disable":
                response = await self._handle_set_enabled(name, False)
            case "delete":
                response = await self._handle_delete(name)
            case "trigger":
                response = await self._handle_trigger(name)
            case _:
                response = "Unknown workflow action."

        return AgentResult(agent=self.name, response=response)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response

    # ── Handlers ─────────────────────────────────────────────────────────────

    async def _handle_create(
        self,
        name: str | None,
        description: str | None,
        schedule_description: str | None,
    ) -> str:
        if not name or not description:
            return "Please provide a name and description to create a workflow."

        try:
            steps = await self._planner.plan(description)
            schedule = await self._planner.extract_schedule(schedule_description or description)
        except WorkflowPlanError as exc:
            return f"Couldn't plan the workflow: {exc}"

        next_run = None
        if schedule:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(schedule)
            next_run = trigger.get_next_fire_time(None, datetime.now(tz=timezone.utc))

        workflow = Workflow(
            id=None,  # type: ignore[arg-type]
            name=name,
            description=description,
            steps=steps,
            schedule=schedule,
            enabled=True,
            last_run_at=None,
            next_run_at=next_run,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        workflow_id = await self._store.create(workflow)
        workflow.id = workflow_id

        await self._scheduler.add_workflow(workflow)

        step_summary = "\n".join(f"  {i+1}. {s.task}" for i, s in enumerate(steps))
        schedule_msg = f"\nSchedule: `{schedule}`" if schedule else "\nNo recurring schedule (on-demand)."
        return (
            f"Workflow **{name}** created with {len(steps)} step(s):\n{step_summary}"
            f"{schedule_msg}"
        )

    async def _handle_list(self) -> str:
        workflows = await self._store.list_all()
        if not workflows:
            return "No workflows stored yet."
        lines = []
        for wf in workflows:
            status = "enabled" if wf.enabled else "disabled"
            sched = f" — `{wf.schedule}`" if wf.schedule else ""
            lines.append(f"- **{wf.name}** ({status}{sched}): {wf.description}")
        return "Workflows:\n" + "\n".join(lines)

    async def _handle_get(self, name: str | None) -> str:
        if not name:
            return "Please specify a workflow name."
        wf = await self._store.get_by_name(name)
        if wf is None:
            return f"No workflow named '{name}' found."
        step_lines = "\n".join(f"  {i+1}. {s.task}" for i, s in enumerate(wf.steps))
        sched = f"`{wf.schedule}`" if wf.schedule else "on-demand only"
        return (
            f"**{wf.name}** ({'enabled' if wf.enabled else 'disabled'})\n"
            f"{wf.description}\n\n"
            f"Schedule: {sched}\n"
            f"Steps:\n{step_lines}"
        )

    async def _handle_set_enabled(self, name: str | None, enabled: bool) -> str:
        if not name:
            return "Please specify a workflow name."
        wf = await self._store.get_by_name(name)
        if wf is None:
            return f"No workflow named '{name}' found."
        await self._store.set_enabled(wf.id, enabled)
        if enabled:
            await self._scheduler.add_workflow(wf)
        else:
            await self._scheduler.remove_workflow(wf.id)
        verb = "enabled" if enabled else "disabled"
        return f"Workflow **{name}** {verb}."

    async def _handle_delete(self, name: str | None) -> str:
        if not name:
            return "Please specify a workflow name."
        wf = await self._store.get_by_name(name)
        if wf is None:
            return f"No workflow named '{name}' found."
        await self._scheduler.remove_workflow(wf.id)
        await self._store.delete(wf.id)
        return f"Workflow **{name}** deleted."

    async def _handle_trigger(self, name: str | None) -> str:
        if not name:
            return "Please specify a workflow name."
        wf = await self._store.get_by_name(name)
        if wf is None:
            return f"No workflow named '{name}' found."
        await self._scheduler.trigger_now(wf.id)
        return f"Workflow **{name}** triggered. Results will be sent when complete."
