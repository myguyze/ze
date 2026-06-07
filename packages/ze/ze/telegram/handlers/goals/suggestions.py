from __future__ import annotations

import asyncio

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.core.delivery import answer_html
from ze.telegram.formatting import bold, esc
from ze_personal.goals.types import SuggestionStatus

log = get_logger(__name__)


async def handle_suggestion(ctx: BotContext, query: CallbackQuery) -> None:
    data = query.data or ""
    parts = data.split(":", 2)
    if len(parts) != 3 or not ctx.goal_suggestion_store:
        await query.answer()
        return

    _, action, short_id = parts
    suggestion = await ctx.goal_suggestion_store.resolve_short_id(short_id)

    if suggestion is None or suggestion.status != SuggestionStatus.PENDING:
        await query.answer("This suggestion is no longer active.")
        return

    if action == "accept":
        await accept_suggestion(ctx, query, suggestion)
    elif action == "dismiss":
        await dismiss_suggestion(ctx, query, suggestion)
    elif action == "more":
        await expand_suggestion(ctx, query, suggestion, short_id)
    else:
        await query.answer()


async def accept_suggestion(ctx: BotContext, query: CallbackQuery, suggestion) -> None:
    await query.answer()
    if not ctx.goal_planner or not ctx.goal_store or not ctx.goal_suggestion_store:
        await query.message.answer("Something went wrong — please try again.")
        return

    try:
        goal = ctx.goal_planner.create_goal_from_suggestion(suggestion)
        goal = await ctx.goal_store.create_goal(goal)
        accepted = await ctx.goal_suggestion_store.mark_accepted(suggestion.id, goal.id)
        if not accepted:
            await query.answer("Already accepted.", show_alert=False)
            return
        await query.message.edit_reply_markup(reply_markup=None)
        await answer_html(
            query.message,
            f"Done — {bold(goal.title)} is now an active goal. "
            f"Ze will begin planning milestones shortly.",
        )
        if ctx.goal_executor:
            task = asyncio.create_task(ctx.goal_executor.advance(goal.id))
            task.add_done_callback(
                lambda t: log.error("goal_suggestion_advance_failed", error=str(t.exception()))
                if t.exception() else None
            )
    except Exception as exc:
        log.error("goal_suggestion_accept_failed", error=str(exc))
        await query.message.answer(
            "Something went wrong creating the goal — the option above is still available."
        )


async def dismiss_suggestion(ctx: BotContext, query: CallbackQuery, suggestion) -> None:
    dismissed = await ctx.goal_suggestion_store.mark_dismissed(suggestion.id)
    if not dismissed:
        await query.answer("Already resolved.", show_alert=False)
        return
    await query.answer("Dismissed.")
    await query.message.edit_reply_markup(reply_markup=None)


async def expand_suggestion(
    ctx: BotContext,
    query: CallbackQuery,
    suggestion,
    short_id: str,
) -> None:
    await query.answer()
    text = (
        f"Here's more context on why I suggested {bold(suggestion.title)}:\n\n"
        f"{esc(suggestion.rationale)}\n\n"
        f"The goal would be: {esc(suggestion.objective)}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Yes, create it",
                callback_data=f"goal_suggest:accept:{short_id}",
            ),
            InlineKeyboardButton(
                text="Dismiss",
                callback_data=f"goal_suggest:dismiss:{short_id}",
            ),
        ],
    ])
    await answer_html(query.message, text, reply_markup=keyboard)
