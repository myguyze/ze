"""Ze Core — convention-based agent framework."""

from ze_core.capability.types import Mode
import ze_core.defaults as defaults
from ze_core.channels import Channel, ChannelRegistry
from ze_core.channels.types import ChannelHandle, ChannelType, Message, SentMessage, Thread, ThreadMessage
from ze_core.container import Container
from ze_core.db import DBPool
from ze_core.errors import (
    ChannelError,
    ChannelNotFoundError,
    OpenRouterError,
    RateLimitError,
)
from ze_core.interface.base import InputPreprocessor
from ze_core.interface.types import Action, Notification, ProcessedInput, RawInput
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
from ze_core.openrouter.client import OpenRouterClient
from ze_core.orchestration import BaseAgent, agent
from ze_core.orchestration.graph import graph_builder
from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.plugin import ZePlugin
from ze_core.settings import Settings

__all__ = [
    "defaults",
    "Mode",
    "Action",
    "InputPreprocessor",
    "Notification",
    "ProcessedInput",
    "RawInput",
    "graph_builder",
    "Channel",
    "ChannelRegistry",
    "ChannelHandle",
    "ChannelError",
    "ChannelNotFoundError",
    "ChannelType",
    "OpenRouterError",
    "RateLimitError",
    "Container",
    "DBPool",
    # Proactive
    "ProactiveNotifier",
    "ProactiveScheduler",
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
    "OpenRouterClient",
    "BaseAgent",
    "agent",
    "ToolAccess",
    "tool",
    "ZePlugin",
    "Settings",
]
