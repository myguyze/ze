import asyncio
import base64
from email.mime.text import MIMEText

from ze_core.orchestration.tool import ToolAccess, tool
from ze_email.channel.gmail import GmailChannel
from ze_core.channels.types import ChannelType, Message
from ze_google.auth import GoogleCredentials


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


@tool(access=ToolAccess.WRITE, description="Send an email via Gmail. Use thread_id to reply in an existing thread.")
async def send_email(
    gmail_channel: GmailChannel,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict:
    msg = Message(
        channel_type=ChannelType.EMAIL,
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
    )
    sent = await gmail_channel.send(msg)
    return {"id": sent.message_id, "thread_id": sent.thread_id}


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
