from __future__ import annotations

import asyncio

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
    for chunk in split_html(html):
        await ctx.bot.send_message(chat_id, chunk, parse_mode="HTML")
