from __future__ import annotations

import asyncio
from typing import Any

from aiogram.types import Message

from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.formatting import md_to_html, split_html
from ze_core.interface.types import OutboundMessage

log = get_logger(__name__)


async def keep_typing(ctx: BotContext, chat_id: int) -> None:
    try:
        while True:
            await ctx.bot.send_chat_action(chat_id, "typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


async def send_html(ctx: BotContext, chat_id: int, text: str, **kwargs: Any) -> None:
    await ctx.bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)


async def send_html_chunks(ctx: BotContext, chat_id: int, text: str, **kwargs: Any) -> None:
    for chunk in split_html(text):
        await ctx.bot.send_message(chat_id, chunk, parse_mode="HTML", **kwargs)


async def answer_html(message: Message, text: str, **kwargs: Any) -> None:
    await message.answer(text, parse_mode="HTML", **kwargs)


async def edit_html(message: Message, text: str, **kwargs: Any) -> None:
    await message.edit_text(text, parse_mode="HTML", **kwargs)


async def deliver_response(ctx: BotContext, chat_id: int, text: str) -> None:
    if not text:
        return
    if ctx.interface is not None:
        ctx.interface.set_chat(chat_id)
        await ctx.interface.send(
            OutboundMessage(content=text, format="markdown"),
        )
        return
    html = md_to_html(text)
    await send_html_chunks(ctx, chat_id, html)
