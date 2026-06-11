import asyncio
import base64
from datetime import datetime, timezone
from email import utils as email_utils
from email.mime.text import MIMEText

import structlog

from ze_core.channels.base import Channel
from ze_core.channels.types import ChannelType, Message, SentMessage, Thread, ThreadMessage
from ze_core.errors import ChannelSendError
from ze_google.auth import GoogleCredentials

log = structlog.get_logger(__name__)


class GmailChannel(Channel):
    def __init__(self, credentials: GoogleCredentials) -> None:
        self._creds = credentials
        self._user_email: str | None = None

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.EMAIL

    async def send(self, message: Message) -> SentMessage:
        try:
            service = self._creds.gmail()
            raw = _build_raw(message.to, message.subject or "", message.body)
            body: dict = {"raw": raw}
            if message.thread_id:
                body["threadId"] = message.thread_id
            result = await asyncio.to_thread(
                lambda: service.users().messages().send(userId="me", body=body).execute()
            )
            sent_msg = await asyncio.to_thread(
                lambda: service.users().messages().get(
                    userId="me",
                    id=result["id"],
                    format="metadata",
                    metadataHeaders=["Date"],
                ).execute()
            )
            return SentMessage(
                message_id=result["id"],
                thread_id=result.get("threadId", result["id"]),
                channel_type=ChannelType.EMAIL,
                sent_at=_parse_date(sent_msg) or datetime.now(timezone.utc),
            )
        except ChannelSendError:
            raise
        except Exception as exc:
            log.warning("gmail_channel_send_failed", error=str(exc))
            raise ChannelSendError(str(exc)) from exc

    async def get_thread(self, thread_id: str) -> Thread:
        user_email = await self._resolve_user_email()
        service = self._creds.gmail()
        raw = await asyncio.to_thread(
            lambda: service.users().threads().get(
                userId="me", id=thread_id, format="full"
            ).execute()
        )
        messages = [
            _parse_thread_message(m, user_email)
            for m in raw.get("messages", [])
        ]
        messages.sort(key=lambda m: m.sent_at)
        return Thread(thread_id=thread_id, channel_type=ChannelType.EMAIL, messages=messages)

    async def poll_replies(
        self,
        thread_ids: list[str],
        since: datetime,
    ) -> list[ThreadMessage]:
        replies: list[ThreadMessage] = []
        for thread_id in thread_ids:
            thread = await self.get_thread(thread_id)
            for msg in thread.messages:
                if not msg.is_outbound and msg.sent_at > since:
                    replies.append(msg)
        return replies

    async def _resolve_user_email(self) -> str:
        if self._user_email is None:
            service = self._creds.gmail()
            profile = await asyncio.to_thread(
                lambda: service.users().getProfile(userId="me").execute()
            )
            self._user_email = profile["emailAddress"]
        return self._user_email


def _build_raw(to: str, subject: str, body: str) -> str:
    msg = MIMEText(body, "plain")
    msg["to"] = to
    msg["subject"] = subject
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


def _parse_date(msg: dict) -> datetime | None:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    date_str = headers.get("Date")
    if not date_str:
        return None
    try:
        return email_utils.parsedate_to_datetime(date_str)
    except Exception:
        return None


def _parse_thread_message(msg: dict, user_email: str) -> ThreadMessage:
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    sender = headers.get("From", "")
    return ThreadMessage(
        message_id=msg["id"],
        sender=sender,
        body=_extract_body(msg.get("payload", {})),
        sent_at=_parse_date(msg) or datetime.now(timezone.utc),
        is_outbound=user_email.lower() in sender.lower(),
    )


def _extract_body(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result
    return ""
