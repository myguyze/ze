from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from ze.telegram.context import BotContext
from ze.telegram.session import ActiveSessionStore


def make_query(data: str, chat_id: int = 1234) -> MagicMock:
    query = MagicMock()
    query.data = data
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.edit_reply_markup = AsyncMock()
    query.message.answer = AsyncMock()
    query.message.chat.id = chat_id
    return query


def make_ctx(**overrides) -> BotContext:
    bot = overrides.pop("bot", None) or MagicMock()
    bot.send_message = AsyncMock()

    defaults = {
        "bot": bot,
        "store": MagicMock(spec=ActiveSessionStore),
        "container": None,
        "graph": MagicMock(),
        "workflow_graph": MagicMock(),
        "router": MagicMock(),
        "capability_gate": MagicMock(),
        "memory_store": MagicMock(),
        "persona_store": MagicMock(),
        "person_store": MagicMock(),
        "workflow_store": MagicMock(),
        "workflow_planner": MagicMock(),
        "openrouter_client": MagicMock(),
        "embedder": MagicMock(),
        "settings": MagicMock(),
        "translations": None,
        "pool": None,
        "contact_channel_store": None,
        "goal_store": None,
        "goal_executor": None,
        "goal_planner": None,
        "goal_suggestion_store": None,
        "interface": None,
    }
    defaults.update(overrides)
    return BotContext(**defaults)
