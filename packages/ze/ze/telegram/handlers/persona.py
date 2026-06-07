from __future__ import annotations

from aiogram.types import CallbackQuery

from ze_core.errors import UnknownDialError, UnknownProfileError
from ze.telegram.commands import parse_persona_command, persona_summary
from ze.telegram.context import BotContext
from ze.telegram.core.delivery import edit_html, send_html
from ze.telegram.formatting import code, esc
from ze.telegram.keyboards import persona_keyboard


async def handle_persona_command(ctx: BotContext, chat_id: int, text: str) -> None:
    subcommand, args = parse_persona_command(text)

    if subcommand == "error":
        await send_html(ctx, chat_id, args[0])
        return

    if subcommand == "profile":
        name = args[0]
        try:
            await ctx.persona_store.set_profile(name)
        except UnknownProfileError:
            profiles = ctx.persona_store.available_profiles()
            await send_html(
                ctx,
                chat_id,
                f"Unknown profile {code(name)}. Available: {', '.join(profiles)}",
            )
            return

    elif subcommand == "dial":
        dial_name, value_str = args
        try:
            await ctx.persona_store.set_dial(dial_name, float(value_str))
        except (UnknownDialError, ValueError) as exc:
            await send_html(ctx, chat_id, esc(str(exc)))
            return

    elif subcommand == "reset":
        await ctx.persona_store.reset_dials()

    summary = await persona_summary(ctx.persona_store)
    state = await ctx.persona_store.get_state()
    profiles = ctx.persona_store.available_profiles()
    keyboard = persona_keyboard(profiles, active=state.profile)
    await send_html(ctx, chat_id, summary, reply_markup=keyboard)


async def handle_persona_callback(ctx: BotContext, query: CallbackQuery) -> None:
    data = query.data or ""
    parts = data.split(":", 2)
    await query.answer()

    if len(parts) == 3 and parts[1] == "profile":
        name = parts[2]
        try:
            await ctx.persona_store.set_profile(name)
        except UnknownProfileError:
            return

    summary = await persona_summary(ctx.persona_store)
    state = await ctx.persona_store.get_state()
    profiles = ctx.persona_store.available_profiles()
    keyboard = persona_keyboard(profiles, active=state.profile)
    await edit_html(query.message, summary, reply_markup=keyboard)
