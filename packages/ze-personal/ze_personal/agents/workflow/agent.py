from __future__ import annotations

from typing import AsyncIterator

from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.capability.types import Mode
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.openrouter.client import OpenRouterClient
from ze_personal.workflow.planner import WorkflowPlanner
from ze_personal.workflow.store import WorkflowStore
from ze_personal.workflow.scheduler import WorkflowScheduler
import ze_personal.agents.workflow.tools  # noqa: F401

_AGENT_INSTRUCTIONS = """\
You manage Ze's stored workflows. A workflow is a named sequence of tasks that runs on
an optional recurring schedule.

Available tools:
- list_workflows: list all stored workflows
- get_workflow: get full details of a workflow by name, including steps
- create_workflow: create a new workflow (workflow_name, description, optional schedule_description)
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
    description = """
      Manages stored workflows and recurring scheduled tasks. Use when the user wants
      to create, list, enable, disable, delete, or manually run a named workflow or
      recurring automated task.
    """
    model = "anthropic/claude-sonnet-4-5"
    vision_capable = True
    timeout = 60
    tools = [
        "list_workflows",
        "get_workflow",
        "create_workflow",
        "enable_workflow",
        "disable_workflow",
        "delete_workflow",
        "trigger_workflow",
    ]
    intent_map = {
        "read": "List or inspect stored workflows.",
        "manage": "Create, enable, disable, delete, or trigger a workflow.",
    }
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
