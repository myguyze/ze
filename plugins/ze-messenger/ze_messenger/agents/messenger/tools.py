import asyncio
import base64
from email.mime.text import MIMEText

from ze_agents.errors import ChannelNotFoundError
from ze_agents.tool import ToolAccess, tool
from ze_communication.channel import InboundChannel
from ze_communication.registry import ChannelRegistry
from ze_communication.types import ChannelType, Message
from ze_google.auth import GoogleCredentials
from ze_personal.channels.thread_channel_map import ThreadChannelMap
from ze_personal.channels.user_channel_store import UserChannelStore


@tool(access=ToolAccess.READ, description="List recent Gmail messages matching a query.")
async def list_emails(
    credentials: GoogleCredentials,
    query: str = "",
    max_results: int = 10,
) -> list:
    service = credentials.gmail()
    result = await asyncio.to_thread(
        lambda: service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results,
        ).execute()
    )
    return result.get("messages", [])


@tool(access=ToolAccess.READ, description="Get the full content of a Gmail message by ID.")
async def get_email(
    credentials: GoogleCredentials,
    message_id: str,
) -> dict:
    service = credentials.gmail()
    msg = await asyncio.to_thread(
        lambda: service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
    )
    return _parse_message(msg)


@tool(access=ToolAccess.WRITE, description="Create a Gmail draft without sending.")
async def draft_email(
    credentials: GoogleCredentials,
    to: str,
    subject: str,
    body: str,
) -> dict:
    service = credentials.gmail()
    raw = _build_raw(to, subject, body)
    result = await asyncio.to_thread(
        lambda: service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()
    )
    return {"id": result.get("id")}


@tool(access=ToolAccess.WRITE, description="Send an email or reply to a thread.")
async def send_email(
    channel_registry: ChannelRegistry,
    thread_channel_map: ThreadChannelMap,
    user_channel_store: UserChannelStore,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict:
    channel = await _resolve_send_channel(
        channel_registry, thread_channel_map, user_channel_store, thread_id
    )
    msg = Message(
        channel_type=ChannelType.EMAIL,
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
    )
    sent = await channel.send(msg)

    if sent.thread_id:
        await thread_channel_map.set(sent.thread_id, channel.channel_id)

    return {
        "message_id": sent.message_id,
        "thread_id": sent.thread_id,
        "sent_from": channel.channel_id,
    }


@tool(access=ToolAccess.WRITE, description="Archive a Gmail message (remove from inbox).")
async def archive_email(
    credentials: GoogleCredentials,
    message_id: str,
) -> None:
    service = credentials.gmail()
    await asyncio.to_thread(
        lambda: service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
    )


async def _resolve_send_channel(
    registry: ChannelRegistry,
    thread_map: ThreadChannelMap,
    user_channels: UserChannelStore,
    thread_id: str | None,
) -> InboundChannel:
    # 1. Thread known → use the account that owns it
    if thread_id:
        channel_id = await thread_map.get(thread_id)
        if channel_id:
            channel = registry.get_inbound_by_id(channel_id)
            if channel is not None:
                return channel

    # 2. Default outbound
    uc = await user_channels.get_default_outbound("email")
    if uc:
        channel = registry.get_inbound_by_id(uc.channel_id)
        if channel is not None:
            return channel

    # 3. Any available email channel
    for channel in registry.inbound_channels():
        if channel.channel_type.value == "email":
            return channel

    raise ChannelNotFoundError("No email channel available")


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = MIMEText(body, "plain")
    msg["to"] = to
    msg["subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _parse_message(msg: dict) -> dict:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _extract_body(msg.get("payload", {}))
    return {
        "id": msg.get("id"),
        "subject": headers.get("Subject", ""),
        "from": headers.get("From", ""),
        "date": headers.get("Date", ""),
        "snippet": msg.get("snippet", ""),
        "body": body,
    }


def _extract_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""
