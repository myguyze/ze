import asyncio
import base64
import time
from email.mime.text import MIMEText

import structlog

from ze.agents.tool import ToolAccess, tool
from ze.agents.types import ToolCall
from ze.channels.email import EmailChannel
from ze.channels.types import ChannelType, Message
from ze.google.auth import GoogleCredentials

log = structlog.get_logger(__name__)


@tool(access=ToolAccess.READ, description="List recent Gmail messages matching a query.")
async def list_emails(
    credentials: GoogleCredentials,
    query: str = "",
    max_results: int = 10,
) -> ToolCall:
    args = {"query": query, "max_results": max_results}
    start = time.monotonic()
    try:
        service = credentials.gmail()
        result = await asyncio.to_thread(
            lambda: service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results,
            ).execute()
        )
        messages = result.get("messages", [])
        return ToolCall(
            tool_name="list_emails",
            args=args,
            result=messages,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("list_emails_failed", error=str(exc))
        return ToolCall(
            tool_name="list_emails",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )


@tool(access=ToolAccess.READ, description="Get the full content of a Gmail message by ID.")
async def get_email(
    credentials: GoogleCredentials,
    message_id: str,
) -> ToolCall:
    args = {"message_id": message_id}
    start = time.monotonic()
    try:
        service = credentials.gmail()
        msg = await asyncio.to_thread(
            lambda: service.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
        )
        parsed = _parse_message(msg)
        return ToolCall(
            tool_name="get_email",
            args=args,
            result=parsed,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("get_email_failed", error=str(exc))
        return ToolCall(
            tool_name="get_email",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )


@tool(access=ToolAccess.WRITE, description="Create a Gmail draft without sending.")
async def draft_email(
    credentials: GoogleCredentials,
    to: str,
    subject: str,
    body: str,
) -> ToolCall:
    args = {"to": to, "subject": subject}
    start = time.monotonic()
    try:
        service = credentials.gmail()
        raw = _build_raw(to, subject, body)
        result = await asyncio.to_thread(
            lambda: service.users().drafts().create(
                userId="me", body={"message": {"raw": raw}}
            ).execute()
        )
        return ToolCall(
            tool_name="draft_email",
            args=args,
            result={"id": result.get("id")},
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("draft_email_failed", error=str(exc))
        return ToolCall(
            tool_name="draft_email",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )


@tool(access=ToolAccess.WRITE, description="Send an email via Gmail. Use thread_id to reply in an existing thread.")
async def send_email(
    email_channel: EmailChannel,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> ToolCall:
    args = {"to": to, "subject": subject}
    start = time.monotonic()
    try:
        msg = Message(
            channel_type=ChannelType.EMAIL,
            to=to,
            subject=subject,
            body=body,
            thread_id=thread_id,
        )
        sent = await email_channel.send(msg)
        return ToolCall(
            tool_name="send_email",
            args=args,
            result={"id": sent.message_id, "thread_id": sent.thread_id},
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("send_email_failed", error=str(exc))
        return ToolCall(
            tool_name="send_email",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )


@tool(access=ToolAccess.WRITE, description="Archive a Gmail message (remove from inbox).")
async def archive_email(
    credentials: GoogleCredentials,
    message_id: str,
) -> ToolCall:
    args = {"message_id": message_id}
    start = time.monotonic()
    try:
        service = credentials.gmail()
        await asyncio.to_thread(
            lambda: service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["INBOX"]},
            ).execute()
        )
        return ToolCall(
            tool_name="archive_email",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=True,
        )
    except Exception as exc:
        log.warning("archive_email_failed", error=str(exc))
        return ToolCall(
            tool_name="archive_email",
            args=args,
            result=None,
            duration_ms=int((time.monotonic() - start) * 1000),
            success=False,
            error=str(exc),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_raw(to: str, subject: str, body: str) -> str:
    """Build a base64url-encoded RFC 2822 plain-text message."""
    msg = MIMEText(body, "plain")
    msg["to"] = to
    msg["subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _parse_message(msg: dict) -> dict:
    """Extract headers and plain-text body from a Gmail API message object."""
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
    """Recursively extract plain-text body from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""
