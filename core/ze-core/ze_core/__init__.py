"""Ze Core — convention-based agent framework."""

from ze_agents.types import Mode
import ze_agents.defaults as defaults
from ze_communication.channel import Channel
from ze_communication.registry import ChannelRegistry
from ze_communication.types import ChannelHandle, ChannelType, Message, SentMessage, Thread, ThreadMessage
from ze_core.container import Container
from ze_core.db import DBPool
from ze_agents.errors import (
    ChannelError,
    ChannelNotFoundError,
    OpenRouterError,
    RateLimitError,
)
from ze_agents.interface.base import InputPreprocessor
from ze_agents.interface.types import Action, Notification, ProcessedInput, RawInput
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
from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_core.orchestration.graph import graph_builder
from ze_agents.tool import ToolAccess, tool
from ze_plugin.plugin import ZePlugin
from ze_agents.settings import Settings

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
