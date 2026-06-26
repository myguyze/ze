"""Tests for WebhookDispatcher and POST /api/v0/webhooks/{source}."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ze_api.webhook import (
    EventDeduplicator,
    WebhookAuthError,
    WebhookDispatcher,
    WebhookSourceNotFoundError,
    collect_plugin_webhook_handlers,
)
from datetime import datetime, timezone

from ze_communication.registry import ChannelRegistry
from ze_communication.types import ChannelType, InboundMessage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_inbound(message_id: str = "msg-1") -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        channel_type=ChannelType.EMAIL,
        sender="alice@example.com",
        subject="Hi",
        body="Hello",
        thread_id="thread-1",
        received_at=datetime.now(timezone.utc),
    )


def _make_push_channel(messages: list[InboundMessage] | None = None, verify_ok: bool = True):
    verifier = MagicMock()
    verifier.verify.return_value = verify_ok
    verifier.parse = AsyncMock(return_value=messages or [])

    channel = MagicMock()
    channel.supports_push = True
    channel.channel_id = "email"
    channel.webhook_verifier.return_value = verifier
    return channel


def _make_registry(channel=None):
    registry = MagicMock(spec=ChannelRegistry)
    registry.get_inbound.return_value = channel
    registry.inbound_channels.return_value = [channel] if channel else []
    return registry


def _make_dispatcher(channel=None, plugin_handlers=None, trigger_spy=None, container=None):
    registry = _make_registry(channel)
    if container is None:
        container = SimpleNamespace(_webhook_processor=None, invoke=AsyncMock())
    dispatcher = WebhookDispatcher(
        channel_registry=registry,
        plugin_handlers=plugin_handlers or {},
        container=container,
        deduplicator=EventDeduplicator(),
    )
    if trigger_spy is not None:
        dispatcher._trigger_messenger = trigger_spy
    return dispatcher


# ── EventDeduplicator ─────────────────────────────────────────────────────────

def test_deduplicator_not_duplicate_initially():
    d = EventDeduplicator()
    assert not d.is_duplicate("email", "msg-1")


def test_deduplicator_duplicate_after_mark():
    d = EventDeduplicator()
    d.mark_seen("email", "msg-1")
    assert d.is_duplicate("email", "msg-1")


def test_deduplicator_different_sources_independent():
    d = EventDeduplicator()
    d.mark_seen("email", "msg-1")
    assert not d.is_duplicate("trading212", "msg-1")


# ── WebhookDispatcher — channel path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_channel_path_triggers_messenger():
    msg = _make_inbound()
    channel = _make_push_channel(messages=[msg])
    triggered = []

    async def fake_trigger(m, cid):
        triggered.append((m, cid))

    dispatcher = _make_dispatcher(channel=channel, trigger_spy=fake_trigger)
    await dispatcher.dispatch("email", b"{}", {})
    await asyncio.sleep(0)  # drain create_task

    assert len(triggered) == 1
    assert triggered[0][0] is msg
    assert triggered[0][1] == "email"


@pytest.mark.asyncio
async def test_dispatch_channel_path_deduplicates():
    msg = _make_inbound()
    channel = _make_push_channel(messages=[msg])
    triggered = []

    async def fake_trigger(m, cid):
        triggered.append(m)

    dispatcher = _make_dispatcher(channel=channel, trigger_spy=fake_trigger)
    await dispatcher.dispatch("email", b"{}", {})
    await dispatcher.dispatch("email", b"{}", {})  # second delivery of same message
    await asyncio.sleep(0)  # drain create_task

    assert len(triggered) == 1


@pytest.mark.asyncio
async def test_dispatch_channel_path_auth_failure_raises():
    channel = _make_push_channel(verify_ok=False)
    dispatcher = _make_dispatcher(channel=channel)

    with pytest.raises(WebhookAuthError):
        await dispatcher.dispatch("email", b"{}", {})


@pytest.mark.asyncio
async def test_dispatch_unknown_source_raises():
    dispatcher = _make_dispatcher()

    with pytest.raises(WebhookSourceNotFoundError):
        await dispatcher.dispatch("unknown_source", b"{}", {})


# ── WebhookDispatcher — plugin path ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_plugin_path_calls_handle():
    handler = MagicMock()
    handler.source_key = "trading212"
    handler.verify.return_value = True
    handler.handle = AsyncMock()

    dispatcher = _make_dispatcher(plugin_handlers={"trading212": handler})
    await dispatcher.dispatch("trading212", b'{"event": "trade"}', {})
    await asyncio.sleep(0)  # drain create_task

    handler.verify.assert_called_once()
    handler.handle.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_plugin_path_auth_failure_raises():
    handler = MagicMock()
    handler.source_key = "trading212"
    handler.verify.return_value = False

    dispatcher = _make_dispatcher(plugin_handlers={"trading212": handler})

    with pytest.raises(WebhookAuthError):
        await dispatcher.dispatch("trading212", b"{}", {})


# ── collect_plugin_webhook_handlers ──────────────────────────────────────────

def test_collect_plugin_handlers_deduplicates():
    from ze_agents.errors import AgentConfigError

    h1 = SimpleNamespace(source_key="dup")
    h2 = SimpleNamespace(source_key="dup")
    plugin_a = SimpleNamespace(webhook_handlers=lambda: [h1])
    plugin_b = SimpleNamespace(webhook_handlers=lambda: [h2])

    with pytest.raises(AgentConfigError, match="Duplicate webhook handler"):
        collect_plugin_webhook_handlers([plugin_a, plugin_b])


def test_collect_plugin_handlers_empty():
    plugin = SimpleNamespace(webhook_handlers=lambda: [])
    result = collect_plugin_webhook_handlers([plugin])
    assert result == {}


@pytest.mark.asyncio
async def test_trigger_messenger_runs_processor_then_invoke():
    from ze_messenger.inbound.processor import SenderClass

    msg = _make_inbound()
    processor = AsyncMock()
    processor.process = AsyncMock(return_value=SenderClass.KNOWN_CONTACT)
    container = SimpleNamespace(_webhook_processor=processor, invoke=AsyncMock())

    dispatcher = WebhookDispatcher(
        channel_registry=_make_registry(),
        plugin_handlers={},
        container=container,
        deduplicator=EventDeduplicator(),
    )

    await dispatcher._trigger_messenger(msg, "email")

    processor.process.assert_awaited_once_with(msg, channel_id="email")
    container.invoke.assert_awaited_once()
    prompt, thread_id = container.invoke.call_args[0]
    assert "alice@example.com" in prompt
    assert thread_id == f"inbound:{msg.message_id}"


@pytest.mark.asyncio
async def test_trigger_messenger_skips_invoke_for_automated():
    from ze_messenger.inbound.processor import SenderClass

    msg = _make_inbound()
    processor = AsyncMock()
    processor.process = AsyncMock(return_value=SenderClass.AUTOMATED)
    container = SimpleNamespace(_webhook_processor=processor, invoke=AsyncMock())

    dispatcher = WebhookDispatcher(
        channel_registry=_make_registry(),
        plugin_handlers={},
        container=container,
        deduplicator=EventDeduplicator(),
    )

    await dispatcher._trigger_messenger(msg, "email")

    processor.process.assert_awaited_once()
    container.invoke.assert_not_awaited()


# ── Route integration ─────────────────────────────────────────────────────────

def _make_app_with_dispatcher(dispatcher: WebhookDispatcher) -> FastAPI:
    from ze_api.api.routes.webhooks import router

    app = FastAPI()
    app.include_router(router)
    container = SimpleNamespace(webhook_dispatcher=dispatcher)
    app.state.container = container
    return app


@pytest.mark.asyncio
async def test_route_returns_ok_on_success():
    from httpx import ASGITransport, AsyncClient

    msg = _make_inbound()
    channel = _make_push_channel(messages=[msg])

    async def noop_trigger(m, cid):
        pass

    dispatcher = _make_dispatcher(channel=channel, trigger_spy=noop_trigger)
    app = _make_app_with_dispatcher(dispatcher)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v0/webhooks/email", content=b"{}", headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_route_returns_401_on_auth_failure():
    channel = _make_push_channel(verify_ok=False)
    dispatcher = _make_dispatcher(channel=channel)
    app = _make_app_with_dispatcher(dispatcher)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/v0/webhooks/email", content=b"{}", headers={})
    assert resp.status_code == 401


def test_route_returns_404_on_unknown_source():
    dispatcher = _make_dispatcher()
    app = _make_app_with_dispatcher(dispatcher)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post("/api/v0/webhooks/nope", content=b"{}", headers={})
    assert resp.status_code == 404
