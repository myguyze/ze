from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram.types import CallbackQuery

from ze.telegram.context import BotContext
from ze.telegram.handlers.confirmation import handle_confirmation
from ze.telegram.handlers.contacts import handle_contact_callback
from ze.telegram.handlers.goals.plan import handle_goal_plan
from ze.telegram.handlers.goals.stuck import handle_stuck
from ze.telegram.handlers.goals.suggestions import handle_suggestion
from ze.telegram.handlers.goals.gates import handle_goal_gate
from ze.telegram.handlers.persona import handle_persona_callback
from ze.telegram.handlers.workflow_plan import handle_plan_callback

CallbackHandler = Callable[[BotContext, CallbackQuery], Awaitable[None]]

ROUTES: list[tuple[str, CallbackHandler]] = [
    ("plan:", handle_plan_callback),
    ("persona:", handle_persona_callback),
    ("contact:", handle_contact_callback),
    ("goal_plan:", handle_goal_plan),
    ("goal_suggest:", handle_suggestion),
    ("goal_stuck:", handle_stuck),
    ("goal:", handle_goal_gate),
    ("confirm:", handle_confirmation),
]


async def dispatch_callback(ctx: BotContext, query: CallbackQuery) -> None:
    data = query.data or ""
    for prefix, handler in ROUTES:
        if data.startswith(prefix):
            await handler(ctx, query)
            return
    await query.answer()
