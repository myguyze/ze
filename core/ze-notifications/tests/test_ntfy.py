import aiohttp
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_notifications.ntfy import NtfyConfig, NtfyNotifier, _encode_deep_link
from ze_notifications.types import Notification


def make_session(status: int = 200) -> MagicMock:
    resp = AsyncMock()
    resp.status = status

    @asynccontextmanager
    async def _post(*args, **kwargs):
        yield resp

    session = MagicMock()
    session.post = _post
    return session


def make_config(token: str | None = "tok") -> NtfyConfig:
    return NtfyConfig(base_url="https://ntfy.sh", topic="ze-test-abc123", token=token)


def make_notifier(token: str | None = "tok", status: int = 200) -> tuple[NtfyNotifier, MagicMock]:
    session = make_session(status)
    notifier = NtfyNotifier(config=make_config(token), session=session)
    return notifier, session


# ── Header tests ──────────────────────────────────────────────────────────────

async def test_push_sends_title_and_priority(caplog):
    posted_headers = {}

    @asynccontextmanager
    async def _post(url, *, data, headers):
        posted_headers.update(headers)
        resp = AsyncMock()
        resp.status = 200
        yield resp

    session = MagicMock()
    session.post = _post
    notifier = NtfyNotifier(config=make_config(), session=session)

    n = Notification(title="Hello", body="World", priority=4)
    await notifier.push(n)

    assert posted_headers["X-Title"] == "Hello"
    assert posted_headers["X-Priority"] == "4"


async def test_push_includes_authorization_when_token_set():
    posted_headers = {}

    @asynccontextmanager
    async def _post(url, *, data, headers):
        posted_headers.update(headers)
        resp = AsyncMock()
        resp.status = 200
        yield resp

    session = MagicMock()
    session.post = _post
    notifier = NtfyNotifier(config=make_config(token="mytoken"), session=session)

    await notifier.push(Notification(title="T", body="B"))

    assert posted_headers["Authorization"] == "Bearer mytoken"


async def test_push_omits_authorization_when_no_token():
    posted_headers = {}

    @asynccontextmanager
    async def _post(url, *, data, headers):
        posted_headers.update(headers)
        resp = AsyncMock()
        resp.status = 200
        yield resp

    session = MagicMock()
    session.post = _post
    config = NtfyConfig(base_url="https://self-hosted.example.com", topic="ze", token=None)
    notifier = NtfyNotifier(config=config, session=session)

    await notifier.push(Notification(title="T", body="B"))

    assert "Authorization" not in posted_headers


async def test_push_sets_tags_header():
    posted_headers = {}

    @asynccontextmanager
    async def _post(url, *, data, headers):
        posted_headers.update(headers)
        resp = AsyncMock()
        resp.status = 200
        yield resp

    session = MagicMock()
    session.post = _post
    notifier = NtfyNotifier(config=make_config(), session=session)

    await notifier.push(Notification(title="T", body="B", tags=["warning", "goal"]))

    assert posted_headers["X-Tags"] == "warning,goal"


async def test_push_sets_click_header_when_data_set():
    posted_headers = {}

    @asynccontextmanager
    async def _post(url, *, data, headers):
        posted_headers.update(headers)
        resp = AsyncMock()
        resp.status = 200
        yield resp

    session = MagicMock()
    session.post = _post
    notifier = NtfyNotifier(config=make_config(), session=session)

    await notifier.push(Notification(title="T", body="B", data={"screen": "chat"}))

    assert posted_headers["X-Click"] == "ze://navigate?screen=chat"


async def test_push_omits_click_header_when_data_none():
    posted_headers = {}

    @asynccontextmanager
    async def _post(url, *, data, headers):
        posted_headers.update(headers)
        resp = AsyncMock()
        resp.status = 200
        yield resp

    session = MagicMock()
    session.post = _post
    notifier = NtfyNotifier(config=make_config(), session=session)

    await notifier.push(Notification(title="T", body="B", data=None))

    assert "X-Click" not in posted_headers


# ── Error swallowing ──────────────────────────────────────────────────────────

async def test_push_swallows_http_4xx(caplog):
    session = make_session(status=403)
    notifier = NtfyNotifier(config=make_config(), session=session)
    # Must not raise
    await notifier.push(Notification(title="T", body="B"))


async def test_push_swallows_http_5xx(caplog):
    session = make_session(status=500)
    notifier = NtfyNotifier(config=make_config(), session=session)
    await notifier.push(Notification(title="T", body="B"))


async def test_push_swallows_connection_error(caplog):
    @asynccontextmanager
    async def _post(*args, **kwargs):
        raise aiohttp.ClientConnectionError("unreachable")
        yield  # make it a generator

    session = MagicMock()
    session.post = _post
    notifier = NtfyNotifier(config=make_config(), session=session)
    await notifier.push(Notification(title="T", body="B"))


# ── Startup validation ────────────────────────────────────────────────────────

def test_init_raises_when_ntfy_sh_and_no_token():
    session = MagicMock()
    config = NtfyConfig(base_url="https://ntfy.sh", topic="ze-test", token=None)
    with pytest.raises(ValueError, match="NTFY_TOKEN"):
        NtfyNotifier(config=config, session=session)


def test_init_ok_when_self_hosted_and_no_token():
    session = MagicMock()
    config = NtfyConfig(base_url="https://ntfy.example.com", topic="ze", token=None)
    NtfyNotifier(config=config, session=session)  # must not raise


# ── Deep link encoding ────────────────────────────────────────────────────────

def test_encode_deep_link_simple():
    url = _encode_deep_link({"screen": "chat"})
    assert url == "ze://navigate?screen=chat"


def test_encode_deep_link_multiple_keys():
    url = _encode_deep_link({"screen": "goal", "goal_id": "abc-123"})
    assert url.startswith("ze://navigate?")
    assert "screen=goal" in url
    assert "goal_id=abc-123" in url


def test_encode_deep_link_encodes_special_chars():
    url = _encode_deep_link({"screen": "goal list"})
    assert "goal+list" in url or "goal%20list" in url
