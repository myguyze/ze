from abc import ABC, abstractmethod
from typing import AsyncIterator

from ze.agents.types import AgentContext, AgentResult


class BaseAgent(ABC):
    name: str  # set by subclass or @register

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent and return a complete result."""

    @abstractmethod
    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """Stream response tokens."""
        # declared as async generator in subclasses
        raise NotImplementedError
        yield  # make mypy happy
