"""Tests for GmailWebhookVerifier."""
from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_communication.webhook import WebhookPayload
from ze_google.webhook import GmailWebhookVerifier


PUBLIC_URL = "https://ze.example.com"
AUDIENCE = f"{PUBLIC_URL}/api/v0/webhooks/email"


def _make_verifier(public_url: str = PUBLIC_URL) -> GmailWebhookVerifier:
    creds = MagicMock()
    return GmailWebhookVerifier(credentials=creds, public_url=public_url)


def _payload(auth_header: str = "Bearer valid-token", body: bytes = b"{}") -> WebhookPayload:
    return WebhookPayload(
        source="email",
        raw_body=body,
        headers={"Authorization": auth_header},
    )


def _pubsub_body(history_id: str = "12345") -> bytes:
    data = base64.b64encode(json.dumps({"emailAddress": "alice@example.com", "historyId": history_id}).encode()).decode()
    return json.dumps({"message": {"data": data, "messageId": "pub-1"}}).encode()


# ── verify() ─────────────────────────────────────────────────────────────────

def test_verify_returns_false_when_no_auth_header():
    verifier = _make_verifier()
    payload = _payload(auth_header="")
    assert verifier.verify(payload) is False


def test_verify_returns_false_when_not_bearer():
    verifier = _make_verifier()
    payload = _payload(auth_header="Basic abc123")
    assert verifier.verify(payload) is False


def test_verify_returns_true_on_valid_jwt():
    verifier = _make_verifier()
    payload = _payload(auth_header="Bearer valid-token")

    with patch("ze_google.webhook.id_token.verify_oauth2_token", return_value={"sub": "123"}):
        result = verifier.verify(payload)

    assert result is True


def test_verify_checks_correct_audience():
    verifier = _make_verifier()
    payload = _payload(auth_header="Bearer valid-token")

    captured = {}

    def fake_verify(token, request, audience):
        captured["audience"] = audience
        return {"sub": "123"}

    with patch("ze_google.webhook.id_token.verify_oauth2_token", side_effect=fake_verify):
        verifier.verify(payload)

    assert captured["audience"] == AUDIENCE


def test_verify_returns_false_on_invalid_jwt():
    verifier = _make_verifier()
    payload = _payload(auth_header="Bearer bad-token")

    with patch("ze_google.webhook.id_token.verify_oauth2_token", side_effect=ValueError("bad jwt")):
        result = verifier.verify(payload)

    assert result is False


# ── parse() ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_returns_empty_on_malformed_body():
    verifier = _make_verifier()
    payload = _payload(body=b"not-json")
    result = await verifier.parse(payload)
    assert result == []


@pytest.mark.asyncio
async def test_parse_returns_empty_on_missing_history_id():
    verifier = _make_verifier()
    body = json.dumps({"message": {"data": base64.b64encode(b"{}").decode()}}).encode()
    payload = _payload(body=body)
    result = await verifier.parse(payload)
    assert result == []


async def _sync_to_thread(fn, *args, **kwargs):
    """Drop-in for asyncio.to_thread that runs the callable synchronously."""
    return fn()


@pytest.mark.asyncio
async def test_parse_fetches_history_and_returns_messages():
    verifier = _make_verifier()
    body = _pubsub_body(history_id="99")
    payload = _payload(body=body)

    fake_msg = {
        "id": "msg-1",
        "threadId": "thread-1",
        "payload": {
            "headers": [
                {"name": "From", "value": "alice@example.com"},
                {"name": "Subject", "value": "Hello"},
                {"name": "Date", "value": "Thu, 26 Jun 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(b"Hi there").decode()},
        },
        "labelIds": ["INBOX"],
    }

    history_response = {
        "history": [{"messagesAdded": [{"message": {"id": "msg-1"}}]}]
    }

    service = MagicMock()
    service.users.return_value.history.return_value.list.return_value.execute.return_value = history_response
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = fake_msg
    verifier._credentials.gmail.return_value = service

    with patch("ze_google.webhook.asyncio.to_thread", side_effect=_sync_to_thread):
        result = await verifier.parse(payload)

    assert len(result) == 1
    assert result[0].message_id == "msg-1"
    assert result[0].sender == "alice@example.com"


@pytest.mark.asyncio
async def test_parse_returns_empty_when_history_api_fails():
    verifier = _make_verifier()
    body = _pubsub_body()
    payload = _payload(body=body)

    service = MagicMock()
    service.users.return_value.history.return_value.list.return_value.execute.side_effect = Exception("API error")
    verifier._credentials.gmail.return_value = service

    with patch("ze_google.webhook.asyncio.to_thread", side_effect=_sync_to_thread):
        result = await verifier.parse(payload)

    assert result == []
