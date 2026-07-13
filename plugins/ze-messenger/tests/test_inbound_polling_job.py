"""Tests for InboundPollingJob."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


from ze_communication.types import ChannelType, InboundMessage
from ze_messenger.jobs.inbound_poll import InboundPollingJob
from ze_personal.channels.types import UserChannel
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_channel(channel_id: str, poll_enabled: bool = True) -> UserChannel:
    return UserChannel(
        id=uuid4(),
        channel_id=channel_id,
        channel_type="email",
        handle="alice@example.com",
        display_name=None,
        is_default_outbound=False,
        poll_enabled=poll_enabled,
        created_at=_now(),
    )


def _inbound(message_id: str = "msg-1") -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        channel_type=ChannelType.EMAIL,
        sender="alice@example.com",
        subject="Hi",
        body="Hello",
        thread_id="t1",
        received_at=_now(),
        headers={},
    )


def _make_channel(
    channel_id: str = "gmail:ze@example.com", supports_push: bool = False, messages=None
):
    ch = MagicMock()
    ch.channel_id = channel_id
    ch.channel_type = ChannelType.EMAIL
    ch.supports_push = supports_push
    ch.poll_new_messages = AsyncMock(return_value=messages or [])
    # GmailChannel lazy-resolves email — mock as async so _poll doesn't crash
    ch._resolve_user_email = AsyncMock(return_value=channel_id)
    return ch


def _make_job(channels=None, user_channels=None, watermark=None, processor=None):
    registry = MagicMock()
    registry.inbound_channels.return_value = channels or []

    watermark_store = AsyncMock()
    watermark_store.get = AsyncMock(return_value=watermark or _now())
    watermark_store.set = AsyncMock()

    user_channel_store = AsyncMock()
    user_channel_store.list_all = AsyncMock(return_value=user_channels or [])
    user_channel_store.upsert = AsyncMock()

    proc = processor or AsyncMock()
    proc.process = AsyncMock()

    job = InboundPollingJob(
        registry=registry,
        watermark_store=watermark_store,
        user_channel_store=user_channel_store,
        processor=proc,
    )
    return job, watermark_store, user_channel_store, proc


async def test_poll_calls_processor_for_each_message():
    msg = _inbound()
    channel = _make_channel(messages=[msg])
    uc = _user_channel(channel.channel_id)
    job, _, _, proc = _make_job(channels=[channel], user_channels=[uc])

    await job.run()

    proc.process.assert_called_once_with(msg, channel_id=channel.channel_id)


async def test_poll_skips_push_channels():
    channel = _make_channel(supports_push=True)
    uc = _user_channel(channel.channel_id)
    job, _, _, proc = _make_job(channels=[channel], user_channels=[uc])

    await job.run()

    channel.poll_new_messages.assert_not_called()
    proc.process.assert_not_called()


async def test_poll_skips_poll_disabled_channels():
    channel = _make_channel()
    uc = _user_channel(channel.channel_id, poll_enabled=False)
    job, _, _, proc = _make_job(channels=[channel], user_channels=[uc])

    await job.run()

    channel.poll_new_messages.assert_not_called()


async def test_poll_updates_watermark_after_messages():
    msg = _inbound()
    channel = _make_channel(messages=[msg])
    uc = _user_channel(channel.channel_id)
    job, watermark_store, _, _ = _make_job(channels=[channel], user_channels=[uc])

    await job.run()

    watermark_store.set.assert_called_once()
    assert watermark_store.set.call_args[0][0] == channel.channel_id


async def test_poll_auto_registers_channel_after_first_poll():
    msg = _inbound()
    channel = _make_channel(messages=[msg])
    uc = _user_channel(channel.channel_id)
    job, _, user_channel_store, _ = _make_job(channels=[channel], user_channels=[uc])

    await job.run()

    user_channel_store.upsert.assert_called_once()


async def test_poll_no_messages_still_updates_watermark():
    channel = _make_channel(messages=[])
    uc = _user_channel(channel.channel_id)
    job, watermark_store, _, _ = _make_job(channels=[channel], user_channels=[uc])

    await job.run()

    watermark_store.set.assert_called_once()


async def test_poll_error_on_channel_does_not_crash_job():
    channel = _make_channel()
    channel.poll_new_messages = AsyncMock(side_effect=RuntimeError("network error"))
    uc = _user_channel(channel.channel_id)
    job, _, _, proc = _make_job(channels=[channel], user_channels=[uc])

    await job.run()  # must not raise

    proc.process.assert_not_called()


async def test_resolve_user_email_error_does_not_crash_job():
    from google.auth.exceptions import RefreshError

    channel = _make_channel()
    channel._resolve_user_email = AsyncMock(
        side_effect=RefreshError("invalid_grant: Bad Request")
    )
    uc = _user_channel(channel.channel_id)
    job, _, _, proc = _make_job(channels=[channel], user_channels=[uc])

    await job.run()  # must not raise

    channel.poll_new_messages.assert_not_called()
    proc.process.assert_not_called()
