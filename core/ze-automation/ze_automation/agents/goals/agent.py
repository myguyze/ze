from __future__ import annotations

from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import Intent, Mode
from ze_agents.types import AgentContext, AgentResult
from ze_automation.goals.executor import GoalExecutor
from ze_automation.goals.planner import GoalPlanner
from ze_automation.goals.postgres import PostgresGoalStore as GoalStore
from ze_agents.client import LLMClient
from ze_sdk.proactive import ProactiveNotifier
import ze_automation.agents.goals.tools  # noqa: F401

_AGENT_INSTRUCTIONS = """\
You are Ze's goal manager. You create, inspect, steer, pause, resume, and abandon long-running goals.

A goal is a multi-week objective Ze executes autonomously, pausing at verification gates for
human approval before continuing.

Available tools:
- list_goals: list all goals with their status
- get_goal_status: get full details and milestone progress for a goal (requires goal_id)
- get_milestone_trace: show the tools Ze called and their results for a specific milestone
  (requires goal_id and milestone_sequence)
- create_goal: propose a new goal plan for user approval (goal_title, objective,
  success_condition; optionally time_horizon and goal_type: custom|outreach|research)
- steer_goal: redirect a running goal with new instructions (goal_id, instruction).
  Use when the user wants to change direction mid-execution without stopping entirely.
  Ze will finish its current step then replan. Only works while goal is ACTIVE.
- pause_goal: pause an active goal (goal_id)
- resume_goal: resume a paused goal and continue execution (goal_id)
- abandon_goal: permanently abandon a goal (goal_id)

Guidelines:
- For status, pause, resume, steer, or abandon: call list_goals first if the user hasn't provided
  a goal ID, so you can identify the correct goal.
- create_goal sends an approval notification to Telegram — tell the user to confirm there.
- Use get_milestone_trace when the user asks what Ze did during a specific step.
- steer_goal only works while the goal is ACTIVE (not AWAITING_GATE). If the goal is awaiting a
  gate, tell the user to resolve the gate first (approve/stop/redirect), then steer.
- Report errors returned by tools clearly.\
"""


@agent
class GoalAgent(BaseAgent):
    name = "goals"
    display_name = "Goals"
    description = """
      Long-term goals and multi-week objectives that Ze executes autonomously.
      Use for: "I want to achieve X over the next month", "help me reach my goal of X",
      "create a goal to X", "set up a project to accomplish X", "show my active goals",
      "how is my goal progressing", "what's the status of my X goal",
      "pause my goal", "resume my goal", "abandon my goal", "steer my goal".
      Not for one-shot reminders, scheduled automations, or calendar events.
    """
    model = "anthropic/claude-sonnet-4-5"
    model_simple = "anthropic/claude-haiku-4-5"
    timeout = 60
    tools = [
        "list_goals",
        "get_goal_status",
        "get_milestone_trace",
        "create_goal",
        "steer_goal",
        "pause_goal",
        "resume_goal",
        "abandon_goal",
    ]
    intents = {
        "create": Intent(Mode.CONFIRM,    "Create a new multi-week goal and decompose it into milestones."),
        "read":   Intent(Mode.AUTONOMOUS, "Inspect goal status, list active goals, or review progress and traces."),
        "update": Intent(Mode.CONFIRM,    "Pause, resume, or redirect (steer) an active goal mid-execution."),
        "delete": Intent(Mode.CONFIRM,    "Abandon a goal."),
    }

    def __init__(
        self,
        openrouter_client: LLMClient,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
        goal_executor: GoalExecutor,
        notifier: ProactiveNotifier,
    ) -> None:
        self._client = openrouter_client
        self._store = goal_store
        self._planner = goal_planner
        self._executor = goal_executor
        self._notifier = notifier

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "goals.managing")
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps={
                "store": self._store,
                "planner": self._planner,
                "executor": self._executor,
                "notifier": self._notifier,
            },
        )
        self._log.info(
            "goal_agent_complete",
            session_id=ctx.session_id,
            tool_calls=len(loop_tool_calls),
        )
        return AgentResult(agent=self.name, response=response, tool_calls=loop_tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response
