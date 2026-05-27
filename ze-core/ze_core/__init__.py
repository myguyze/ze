"""Ze Core — convention-based agent framework."""

from ze_core.capability.types import Mode
import ze_core.defaults as defaults
from ze_core.channels import Channel, ChannelRegistry
from ze_core.channels.types import ChannelHandle, Message, SentMessage, Thread, ThreadMessage
from ze_core.container import Container
from ze_core.db import DBPool
from ze_core.errors import (
    ChannelError,
    ChannelNotFoundError,
    GoalError,
    GoalExecutionError,
    GoalPlanError,
    PersonaError,
    UnknownDialError,
    UnknownProfileError,
)
from ze_core.goals import (
    Goal,
    GoalExecutor,
    GoalLearning,
    GoalPlanner,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
    VerificationGate,
)
from ze_core.goals.store import GoalStore
from ze_core.goals.postgres import PostgresGoalStore
from ze_core.interface.types import Action, Notification
from ze_core.memory import MemoryConsolidator, MemoryStore
from ze_core.persona import PersonaState, PersonaStore, PostgresPersonaStore
from ze_core.proactive import ProactiveNotifier, ProactiveScheduler
from ze_core.telemetry import (
    CostContext,
    CostRecord,
    CostReconciler,
    CostStore,
    CostTracker,
    PostgresCostStore,
    SQLiteCostStore,
    UsageInfo,
    get_cost_context,
    set_agent_context,
    set_flow_context,
)
from ze_core.memory.postgres import PostgresMemoryStore
from ze_core.memory.sqlite import SQLiteMemoryStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.orchestration import BaseAgent, agent
from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.settings import Settings

__all__ = [
    "defaults",
    "Mode",
    "Action",
    "Notification",
    "Channel",
    "ChannelRegistry",
    "ChannelHandle",
    "ChannelError",
    "ChannelNotFoundError",
    "Container",
    "DBPool",
    # Goals
    "Goal",
    "GoalExecutor",
    "GoalLearning",
    "GoalPlanner",
    "GoalStatus",
    "GateStatus",
    "Milestone",
    "MilestoneStatus",
    "VerificationGate",
    "GoalStore",
    "PostgresGoalStore",
    "GoalError",
    "GoalExecutionError",
    "GoalPlanError",
    # Persona
    "PersonaState",
    "PersonaStore",
    "PostgresPersonaStore",
    "PersonaError",
    "UnknownDialError",
    "UnknownProfileError",
    # Proactive
    "ProactiveNotifier",
    "ProactiveScheduler",
    # Memory
    "MemoryConsolidator",
    "Message",
    "SentMessage",
    "Thread",
    "ThreadMessage",
    "CostContext",
    "CostRecord",
    "CostReconciler",
    "CostStore",
    "CostTracker",
    "PostgresCostStore",
    "SQLiteCostStore",
    "UsageInfo",
    "get_cost_context",
    "set_agent_context",
    "set_flow_context",
    "MemoryStore",
    "PostgresMemoryStore",
    "SQLiteMemoryStore",
    "OpenRouterClient",
    "BaseAgent",
    "agent",
    "ToolAccess",
    "tool",
    "Settings",
]
