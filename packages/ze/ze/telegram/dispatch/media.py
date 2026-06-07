from __future__ import annotations

from io import BytesIO

from aiogram.types import Message

from ze.errors import ImageDownloadError
from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.core.turn import ingest_raw
from ze_core.interface.types import RawInput
from ze_core.telemetry.context import set_flow_context

log = get_logger(__name__)


async def dispatch_voice(ctx: BotContext, message: Message) -> None:
    chat_id = message.chat.id

    if ctx.store.is_active(chat_id):
        await ctx.bot.send_message(chat_id, "A task is already in progress.")
        return

    voice = message.voice or message.audio
    if not voice:
        return

    file = await ctx.bot.get_file(voice.file_id)
    buffer = BytesIO()
    await ctx.bot.download_file(file.file_path, buffer)
    audio_bytes = buffer.getvalue()

    ctx.store.mark_active(chat_id)
    set_flow_context("user_message", str(chat_id))
    log.info("voice_received", chat_id=chat_id, bytes=len(audio_bytes))

    await ingest_raw(
        ctx,
        chat_id,
        RawInput(audio=audio_bytes, audio_mime="audio/ogg"),
    )


async def dispatch_photo(ctx: BotContext, message: Message) -> None:
    chat_id = message.chat.id

    if ctx.store.is_active(chat_id):
        await ctx.bot.send_message(chat_id, "A task is already in progress.")
        return

    if not message.photo:
        return

    photo = message.photo[-1]
    if photo.file_size and photo.file_size > 8_388_608:
        await ctx.bot.send_message(chat_id, "Image is too large to process (max 8 MB).")
        return

    try:
        file = await ctx.bot.get_file(photo.file_id)
        buffer = BytesIO()
        await ctx.bot.download_file(file.file_path, buffer)
        image_bytes = buffer.getvalue()
    except Exception as exc:
        log.warning("image_download_failed", chat_id=chat_id, error=str(exc))
        raise ImageDownloadError(str(exc)) from exc

    ctx.store.mark_active(chat_id)
    set_flow_context("user_message", str(chat_id))
    log.info("photo_received", chat_id=chat_id, file_size=photo.file_size)

    caption = message.caption or ""
    await ingest_raw(
        ctx,
        chat_id,
        RawInput(
            text=caption or None,
            image=image_bytes,
            image_mime="image/jpeg",
        ),
    )
