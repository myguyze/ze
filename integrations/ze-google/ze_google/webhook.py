from __future__ import annotations

import asyncio
import base64
import json

import structlog
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from ze_communication.types import ChannelType, InboundMessage
from ze_communication.webhook import WebhookPayload, WebhookVerifier

log = structlog.get_logger(__name__)


class GmailWebhookVerifier(WebhookVerifier):
    """Verifies Google Cloud Pub/Sub push messages via OIDC JWT."""

    def __init__(self, credentials: object, public_url: str) -> None:
        self._credentials = credentials
        # Audience is the full webhook URL
        self._audience = f"{public_url.rstrip('/')}/api/v0/webhooks/email"

    def verify(self, payload: WebhookPayload) -> bool:
        auth_header = payload.headers.get("authorization") or payload.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            log.warning("gmail_webhook_missing_bearer")
            return False
        token = auth_header[len("Bearer "):]
        try:
            id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                audience=self._audience,
            )
            return True
        except Exception as exc:
            log.warning("gmail_webhook_jwt_invalid", error=str(exc))
            return False

    async def parse(self, payload: WebhookPayload) -> list[InboundMessage]:
        try:
            envelope = json.loads(payload.raw_body)
            data_b64 = envelope.get("message", {}).get("data", "")
            data = json.loads(base64.b64decode(data_b64 + "==").decode())
            history_id = str(data["historyId"])
        except Exception as exc:
            log.warning("gmail_webhook_parse_failed", error=str(exc))
            return []

        return await self._fetch_history(history_id)

    async def _fetch_history(self, start_history_id: str) -> list[InboundMessage]:
        from ze_google.gmail_channel import _parse_inbound_message

        service = self._credentials.gmail()  # type: ignore[attr-defined]
        try:
            result = await asyncio.to_thread(
                lambda: service.users().history().list(
                    userId="me",
                    startHistoryId=start_history_id,
                    historyTypes=["messageAdded"],
                    labelId="INBOX",
                ).execute()
            )
        except Exception as exc:
            log.warning("gmail_webhook_history_failed", error=str(exc), history_id=start_history_id)
            return []

        messages: list[InboundMessage] = []
        for record in result.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id = added["message"]["id"]
                try:
                    full = await asyncio.to_thread(
                        lambda mid=msg_id: service.users().messages().get(
                            userId="me", id=mid, format="full"
                        ).execute()
                    )
                    messages.append(_parse_inbound_message(full))
                except Exception as exc:
                    log.warning("gmail_webhook_message_fetch_failed", message_id=msg_id, error=str(exc))
        return messages
