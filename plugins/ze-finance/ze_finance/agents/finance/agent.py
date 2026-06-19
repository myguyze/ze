from __future__ import annotations

from typing import AsyncIterator

import ze_finance.agents.finance.tools  # noqa: F401

from ze_agents.base_agent import BaseAgent
from ze_agents.client import LLMClient
from ze_agents.registry import agent
from ze_agents.types import AgentContext, AgentResult
from ze_finance.store import PortfolioStore, TransactionStore

_AGENT_INSTRUCTIONS = """\
You are Ze's finance assistant. You have access to the user's investment portfolio
and bank transaction history.

Use the available tools to answer portfolio questions accurately. Always state the
reference date of the data — positions are point-in-time snapshots, not live prices.
Never speculate about future prices or give investment advice.

For questions about factor risk, concentration, or exposure analysis, tell the user
that risk analysis will be available in a future update.
"""


@agent
class FinanceAgent(BaseAgent):
    description = "Answers questions about investment portfolio, positions, P&L, and spending"
    # Pinned to Anthropic — financial data must not reach other providers.
    model = "anthropic/claude-haiku-4-5"
    intents = [
        "portfolio", "positions", "investments", "P&L", "returns",
        "spending", "transactions", "balance", "Trading212",
        "how much", "how is my", "what did I spend",
    ]
    tools = [
        "get_portfolio_summary",
        "get_positions",
        "get_spending_summary",
        "get_transactions",
        "get_account_balance",
    ]
    timeout = 60

    def __init__(
        self,
        client: LLMClient,
        portfolio_store: PortfolioStore,
        transaction_store: TransactionStore,
    ) -> None:
        self._client = client
        self._portfolio_store = portfolio_store
        self._transaction_store = transaction_store

    async def run(self, ctx: AgentContext) -> AgentResult:
        deps = {
            "portfolio_store": self._portfolio_store,
            "transaction_store": self._transaction_store,
            "reporter": ctx.reporter,
        }
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps=deps,
        )
        return AgentResult(agent="finance", response=response, tool_calls=tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response
