from ze_automation.goals.types import (
    Goal,
    GoalConvergence,
    GoalLearning,
    GoalStatus,
    GoalSuggestion,
    GateStatus,
    ExecutionTrace,
    Milestone,
    MilestoneStatus,
    PriorMilestoneOutput,
    StuckGoal,
    SuggestionStatus,
    VerificationGate,
)
from ze_automation.goals.store import GoalStore
from ze_automation.goals.postgres import PostgresGoalStore
from ze_automation.goals.suggestion_store import GoalSuggestionStore
from ze_automation.goals.planner import GoalPlanner
from ze_automation.goals.executor import GoalExecutor
from ze_automation.workflow.types import Workflow, WorkflowStep, WorkflowExecution, StepResult
from ze_automation.workflow.store import WorkflowStore
from ze_automation.workflow.postgres import PostgresWorkflowStore
from ze_automation.workflow.scheduler import WorkflowScheduler
from ze_automation.workflow.planner import WorkflowPlanner
from ze_automation.runtime.contracts import AutomationPlanner, AutomationStore


def agent_module_paths() -> list[str]:
    """Return module paths for goal and workflow agent registration."""
    return [
        "ze_automation.agents.goals.tools",
        "ze_automation.agents.goals.agent",
        "ze_automation.agents.workflow.tools",
        "ze_automation.agents.workflow.agent",
    ]


__all__ = [
    "Goal",
    "GoalConvergence",
    "GoalLearning",
    "GoalStatus",
    "GoalSuggestion",
    "GoalSuggestionStore",
    "GateStatus",
    "ExecutionTrace",
    "Milestone",
    "MilestoneStatus",
    "PriorMilestoneOutput",
    "StuckGoal",
    "SuggestionStatus",
    "VerificationGate",
    "GoalStore",
    "PostgresGoalStore",
    "GoalPlanner",
    "GoalExecutor",
    "Workflow",
    "WorkflowStep",
    "WorkflowExecution",
    "StepResult",
    "WorkflowStore",
    "PostgresWorkflowStore",
    "WorkflowScheduler",
    "WorkflowPlanner",
    "AutomationPlanner",
    "AutomationStore",
    "agent_module_paths",
]
