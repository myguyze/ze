import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ze_email.channel.gmail import GmailChannel
from ze_core.channels.types import ChannelType, Message, SentMessage, ThreadMessage
from ze_core.errors import ChannelSendError


# ── Helpers ───────────────────────────────────────────────────────────────────

_USER_EMAIL = "ze@example.com"
_DATE_STR = "Mon, 25 May 2026 10:00:00 +0000"
_DATE_DT = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)


def _encode_body(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _make_gmail_message(
    msg_id: str,
    sender: str,
    body_text: str,
    date: str = _DATE_STR,
) -> dict:
    return {
        "id": msg_id,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
            ],
            "body": {"data": _encode_body(body_text)},
            "parts": [],
        },
    }


def _make_credentials(
    profile_email: str = _USER_EMAIL,
    send_result: dict | None = None,
    sent_msg: dict | None = None,
    thread_result: dict | None = None,
) -> MagicMock:
    service = MagicMock()
    # getProfile
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": profile_email
    }
    # messages.send
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = (
        send_result or {"id": "msg1", "threadId": "thread1"}
    )
    # messages.get (for sent timestamp)
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = (
        sent_msg or _make_gmail_message("msg1", _USER_EMAIL, "hello")
    )
    # threads.get
    service.users.return_value.threads.return_value.get.return_value.execute.return_value = (
        thread_result or {"messages": []}
    )
    creds = MagicMock()
    creds.gmail.return_value = service
    return creds


def _channel(creds: MagicMock | None = None) -> GmailChannel:
    return GmailChannel(credentials=creds or _make_credentials())


# ── channel_type ──────────────────────────────────────────────────────────────

def test_channel_type():
    assert _channel().channel_type == ChannelType.EMAIL


# ── send() ────────────────────────────────────────────────────────────────────

async def test_send_returns_sent_message():
    creds = _make_credentials(
        send_result={"id": "msg1", "threadId": "thread1"},
        sent_msg=_make_gmail_message("msg1", _USER_EMAIL, "hi"),
    )
    ch = _channel(creds)
    msg = Message(channel_type=ChannelType.EMAIL, to="alice@example.com", subject="Hi", body="hello")
    result = await ch.send(msg)
    assert isinstance(result, SentMessage)
    assert result.message_id == "msg1"
    assert result.thread_id == "thread1"
    assert result.channel_type == ChannelType.EMAIL


async def test_send_attaches_thread_id_when_provided():
    creds = _make_credentials()
    service = creds.gmail.return_value
    ch = _channel(creds)
    msg = Message(
        channel_type=ChannelType.EMAIL,
        to="alice@example.com",
        subject="Re: Hi",
        body="reply",
        thread_id="existing-thread",
    )
    await ch.send(msg)
    call_kwargs = service.users.return_value.messages.return_value.send.call_args
    body_arg = call_kwargs.kwargs.get("body") or call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs["body"]
    assert body_arg.get("threadId") == "existing-thread"


async def test_send_omits_thread_id_when_none():
    creds = _make_credentials()
    service = creds.gmail.return_value
    ch = _channel(creds)
    msg = Message(channel_type=ChannelType.EMAIL, to="alice@example.com", body="hello")
    await ch.send(msg)
    call_kwargs = service.users.return_value.messages.return_value.send.call_args
    body_arg = call_kwargs.kwargs.get("body") or call_kwargs.kwargs["body"]
    assert "threadId" not in body_arg


async def test_send_raises_channel_send_error_on_failure():
    creds = _make_credentials()
    creds.gmail.return_value.users.return_value.messages.return_value.send.return_value.execute.side_effect = (
        Exception("network error")
    )
    ch = _channel(creds)
    with pytest.raises(ChannelSendError, match="network error"):
        await ch.send(Message(channel_type=ChannelType.EMAIL, to="x@x.com", body="hi"))


# ── get_thread() ──────────────────────────────────────────────────────────────

async def test_get_thread_parses_messages():
    inbound = _make_gmail_message("m1", "alice@example.com", "Hey!")
    outbound = _make_gmail_message("m2", _USER_EMAIL, "Hi back!")
    creds = _make_credentials(thread_result={"messages": [inbound, outbound]})
    ch = _channel(creds)
    thread = await ch.get_thread("thread1")
    assert thread.thread_id == "thread1"
    assert thread.channel_type == ChannelType.EMAIL
    assert len(thread.messages) == 2


async def test_get_thread_sets_is_outbound_correctly():
    inbound = _make_gmail_message("m1", "alice@example.com", "Hey!")
    outbound = _make_gmail_message("m2", _USER_EMAIL, "Hi back!")
    creds = _make_credentials(thread_result={"messages": [inbound, outbound]})
    ch = _channel(creds)
    thread = await ch.get_thread("thread1")
    by_id = {m.message_id: m for m in thread.messages}
    assert by_id["m1"].is_outbound is False
    assert by_id["m2"].is_outbound is True


async def test_get_thread_sorts_by_date():
    earlier = _make_gmail_message("m1", "alice@example.com", "first", "Mon, 25 May 2026 09:00:00 +0000")
    later = _make_gmail_message("m2", _USER_EMAIL, "second", "Mon, 25 May 2026 11:00:00 +0000")
    creds = _make_credentials(thread_result={"messages": [later, earlier]})
    ch = _channel(creds)
    thread = await ch.get_thread("t1")
    assert thread.messages[0].message_id == "m1"
    assert thread.messages[1].message_id == "m2"


async def test_get_thread_empty():
    creds = _make_credentials(thread_result={"messages": []})
    ch = _channel(creds)
    thread = await ch.get_thread("t1")
    assert thread.messages == []


# ── poll_replies() ────────────────────────────────────────────────────────────

async def test_poll_replies_returns_inbound_after_since():
    inbound = _make_gmail_message("m1", "alice@example.com", "reply", "Mon, 25 May 2026 12:00:00 +0000")
    outbound = _make_gmail_message("m2", _USER_EMAIL, "original", "Mon, 25 May 2026 10:00:00 +0000")
    creds = _make_credentials(thread_result={"messages": [outbound, inbound]})
    ch = _channel(creds)
    since = datetime(2026, 5, 25, 11, 0, 0, tzinfo=timezone.utc)
    replies = await ch.poll_replies(["thread1"], since=since)
    assert len(replies) == 1
    assert replies[0].message_id == "m1"


async def test_poll_replies_excludes_outbound():
    outbound = _make_gmail_message("m1", _USER_EMAIL, "my message", "Mon, 25 May 2026 12:00:00 +0000")
    creds = _make_credentials(thread_result={"messages": [outbound]})
    ch = _channel(creds)
    since = datetime(2026, 5, 25, 0, 0, 0, tzinfo=timezone.utc)
    replies = await ch.poll_replies(["thread1"], since=since)
    assert replies == []


async def test_poll_replies_excludes_messages_before_since():
    inbound = _make_gmail_message("m1", "alice@example.com", "old reply", "Mon, 25 May 2026 08:00:00 +0000")
    creds = _make_credentials(thread_result={"messages": [inbound]})
    ch = _channel(creds)
    since = datetime(2026, 5, 25, 10, 0, 0, tzinfo=timezone.utc)
    replies = await ch.poll_replies(["thread1"], since=since)
    assert replies == []


async def test_poll_replies_empty_thread_ids():
    ch = _channel()
    replies = await ch.poll_replies([], since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert replies == []


async def test_poll_replies_across_multiple_threads():
    reply1 = _make_gmail_message("m1", "alice@example.com", "r1", "Mon, 25 May 2026 12:00:00 +0000")
    reply2 = _make_gmail_message("m2", "bob@example.com", "r2", "Mon, 25 May 2026 13:00:00 +0000")

    service = MagicMock()
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": _USER_EMAIL
    }
    service.users.return_value.threads.return_value.get.return_value.execute.side_effect = [
        {"messages": [reply1]},
        {"messages": [reply2]},
    ]
    creds = MagicMock()
    creds.gmail.return_value = service
    ch = GmailChannel(credentials=creds)

    since = datetime(2026, 5, 25, 11, 0, 0, tzinfo=timezone.utc)
    replies = await ch.poll_replies(["t1", "t2"], since=since)
    assert {r.message_id for r in replies} == {"m1", "m2"}


# ── _resolve_user_email() — caching ──────────────────────────────────────────

async def test_user_email_resolved_only_once():
    creds = _make_credentials()
    service = creds.gmail.return_value
    ch = _channel(creds)
    await ch.get_thread("t1")
    await ch.get_thread("t2")
    assert service.users.return_value.getProfile.return_value.execute.call_count == 1
