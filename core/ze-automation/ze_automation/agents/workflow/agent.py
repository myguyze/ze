from __future__ import annotations

from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import Intent, Mode
from ze_agents.types import AgentContext, AgentResult
from ze_agents.client import LLMClient
from ze_automation.workflow.planner import WorkflowPlanner
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.scheduler import WorkflowScheduler
import ze_automation.agents.workflow.tools  # noqa: F401

_AGENT_INSTRUCTIONS = """\
You manage Ze's stored workflows. A workflow is a named sequence of tasks that runs on
an optional recurring schedule.

Available tools:
- list_workflows: list all stored workflows
- get_workflow: get full details of a workflow by name, including steps
- create_workflow: create a new workflow (workflow_name, description, optional schedule_description)
- update_workflow: change a workflow's schedule (workflow_name, schedule_description)
- enable_workflow / disable_workflow: toggle a workflow on or off (workflow_name)
- delete_workflow: remove a workflow permanently (workflow_name)
- trigger_workflow: run a workflow immediately outside its schedule (workflow_name)

Guidelines:
- When creating, provide a clear workflow_name and description; describe any schedule in natural
  language (e.g. "every Monday at 8am") via schedule_description.
- When the user refers to a workflow by name, pass it as workflow_name exactly as given; if
  ambiguous, call list_workflows first to confirm.
- Summarise create results as: name, step count, and schedule (or "on-demand").
- Report errors returned by tools clearly to the user.\
"""


@agent
class WorkflowManagerAgent(BaseAgent):
    name = "workflow"
    display_name = "Workflows"
    description = """
      Stored named automation workflows and multi-step recurring tasks — not calendar events.
      Use for: "run the X workflow", "execute the X automation now", "trigger the X workflow",
      "run my stored workflow called X", "fire the X workflow immediately",
      "create a workflow that does X every day", "automate X on a schedule",
      "list my workflows", "list my automations", "show me my saved workflows",
      "enable/disable the Y workflow", "change when the X workflow runs",
      "delete the Z automation", "set up a recurring task".
      Not for one-off reminders (use reminders), long-term goals, or Google Calendar events.
    """
    model = "anthropic/claude-sonnet-4-5"
    vision_capable = True
    timeout = 60
    tools = [
        "list_workflows",
        "get_workflow",
        "create_workflow",
        "update_workflow",
        "enable_workflow",
        "disable_workflow",
        "delete_workflow",
        "trigger_workflow",
    ]
    intents = {
        "read":   Intent(Mode.AUTONOMOUS, "List or inspect stored workflows."),
        "manage": Intent(Mode.CONFIRM,    "Create, update, enable, disable, delete, or trigger a workflow."),
    }

    def __init__(
        self,
        openrouter_client: LLMClient,
        workflow_store: WorkflowStore,
        workflow_planner: WorkflowPlanner,
        workflow_scheduler: WorkflowScheduler,
    ) -> None:
        self._client = openrouter_client
        self._store = workflow_store
        self._planner = workflow_planner
        self._scheduler = workflow_scheduler

    async def run(self, ctx: AgentContext) -> AgentResult:
        key = "workflow.managing" if ctx.intent == "manage" else "workflow.reading"
        await self.emit(ctx, key)
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps={
                "store": self._store,
                "planner": self._planner,
                "scheduler": self._scheduler,
            },
        )
        self._log.info(
            "workflow_agent_complete",
            session_id=ctx.session_id,
            tool_calls=len(loop_tool_calls),
        )
        return AgentResult(agent=self.name, response=response, tool_calls=loop_tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response
