from __future__ import annotations

from typing import AsyncIterator

import ze_finance.agents.finance.tools  # noqa: F401

from ze_agents.base_agent import BaseAgent
from ze_agents.client import LLMClient
from ze_agents.registry import agent
from ze_agents.types import AgentContext, AgentResult
from ze_finance.recurring.store import RecurringStore
from ze_finance.store import PortfolioStore, TransactionStore

_AGENT_INSTRUCTIONS = """\
You are Ze's finance assistant. You have access to the user's investment portfolio,
bank transaction history, and detected recurring expenses.

Use the available tools to answer portfolio and spending questions accurately. Always
state the reference date of the data — positions are point-in-time snapshots, not
live prices. Never speculate about future prices or give investment advice.

For recurring expense questions ("what subscriptions do I have?", "what are my fixed
costs?"), call get_recurring_expenses. When the user confirms a charge as a
subscription, call confirm_recurring. When they want to dismiss one, call
dismiss_recurring. After surfacing detected recurring items, use render_confirm with
clear "Yes, track it" / "Ignore" actions so the user can review them inline.

For questions about factor risk, concentration, or exposure analysis, tell the user
that risk analysis will be available in a future update.
"""


@agent
class FinanceAgent(BaseAgent):
    name = "finance"
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
        "get_recurring_expenses",
        "confirm_recurring",
        "dismiss_recurring",
        "render_confirm",
        "render_list",
    ]
    timeout = 60

    def __init__(
        self,
        client: LLMClient,
        portfolio_store: PortfolioStore,
        transaction_store: TransactionStore,
        recurring_store: RecurringStore,
    ) -> None:
        self._client = client
        self._portfolio_store = portfolio_store
        self._transaction_store = transaction_store
        self._recurring_store = recurring_store

    async def run(self, ctx: AgentContext) -> AgentResult:
        deps = {
            "portfolio_store": self._portfolio_store,
            "transaction_store": self._transaction_store,
            "recurring_store": self._recurring_store,
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
