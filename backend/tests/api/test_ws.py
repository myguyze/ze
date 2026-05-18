"""Tests for ze/api/ws.py — the WebSocket endpoint."""
import asyncio
import json
import pathlib
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ze.api import ws as ws_module
from ze.agents.types import AgentResult
from ze.logging import configure_logging
from ze.routing.types import RoutingEnvelope, SubTask
from ze.settings import Settings, get_settings


# ── Helpers ───────────────────────────────────────────────────────────────────

API_KEY = "test-api-key"
SESSION = "session1"


def _make_settings(api_key: str = API_KEY) -> Settings:
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="sk-test",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
        ze_api_key=api_key,
    )


def _make_envelope(agent: str = "companion") -> RoutingEnvelope:
    return RoutingEnvelope(
        primary_agent=agent,
        confidence=0.9,
        score_gap=0.4,
        routing_method="embedding",
        is_compound=False,
        subtasks=[SubTask(agent=agent, intent="reason", prompt="test prompt")],
        requires_synthesis=False,
    )


def _final_state(agent: str = "companion", response: str = "Hello") -> dict:
    return {
        "envelope": _make_envelope(agent),
        "agent_result": AgentResult(agent=agent, response=response),
    }


def _collect(ws, stop_on: set[str] | None = None, max_msgs: int = 30) -> list[dict]:
    """Collect messages from the WS until a terminal type is received."""
    terminal = stop_on or {"done", "error", "confirmation_request"}
    msgs: list[dict] = []
    for _ in range(max_msgs):
        msg = ws.receive_json()
        msgs.append(msg)
        if msg["type"] in terminal:
            break
    return msgs


# ── Fake graph implementations ────────────────────────────────────────────────

class _SimpleGraph:
    """Runs to completion: streams tokens then signals done."""

    def __init__(self, tokens: list[str] | None = None, response: str = "Hello"):
        self._tokens = tokens if tokens is not None else ["Hello"]
        self._response = response

    async def ainvoke(self, state, config):
        queue = config["configurable"]["token_queue"]
        for t in self._tokens:
            await queue.put(t)
        await queue.put(None)  # sentinel
        return _final_state(response=self._response)

    async def aget_state(self, config):
        s = MagicMock()
        s.next = None
        return s

    async def aupdate_state(self, config, update):
        pass


class _ErrorGraph:
    """Raises during ainvoke."""

    async def ainvoke(self, state, config):
        raise RuntimeError("graph exploded")

    async def aget_state(self, config):
        s = MagicMock()
        s.next = None
        return s

    async def aupdate_state(self, config, update):
        pass


class _ConfirmingGraph:
    """First ainvoke triggers a confirmation interrupt; second resumes with tokens."""

    def __init__(self):
        self._calls = 0

    async def ainvoke(self, state, config):
        self._calls += 1
        queue = config["configurable"]["token_queue"]
        if state is None:  # resume path
            await queue.put("Final")
            await queue.put(None)
            return _final_state(response="Final")
        else:  # first call (draft)
            await queue.put(None)  # no streaming in draft mode
            return _final_state(response="Draft content")

    async def aget_state(self, config):
        s = MagicMock()
        # Truthy next signals the graph is interrupted awaiting confirmation
        s.next = ["await_confirmation"] if self._calls == 1 else None
        return s

    async def aupdate_state(self, config, update):
        pass


# ── App factory ───────────────────────────────────────────────────────────────

def _make_app(graph, settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_api_websocket_route("/ws/{session_id}", ws_module.websocket_endpoint)
    app.state.router = MagicMock()
    app.state.capability_gate = MagicMock()
    app.state.memory_store = MagicMock()
    app.state.openrouter_client = MagicMock()
    app.state.embedder = MagicMock()
    app.state.graph = graph
    return app


@contextmanager
def _ws_client(graph, settings: Settings):
    ws_module._sessions.clear()
    app = _make_app(graph, settings)
    with patch("ze.api.dependencies.get_settings", return_value=settings):
        with TestClient(app) as client:
            yield client
    ws_module._sessions.clear()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _logging():
    configure_logging()


@pytest.fixture
def settings() -> Settings:
    s = _make_settings()
    yield s
    get_settings.cache_clear()


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_auth_rejected_when_no_token_provided(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{SESSION}") as ws:
                pass
        assert exc_info.value.code == 4401


def test_auth_rejected_when_wrong_token(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/ws/{SESSION}?token=wrong") as ws:
                pass
        assert exc_info.value.code == 4401


def test_auth_accepted_via_query_param(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            msgs = _collect(ws)
    assert any(m["type"] == "done" for m in msgs)


def test_auth_accepted_via_bearer_header(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(
            f"/ws/{SESSION}", headers={"Authorization": f"Bearer {API_KEY}"}
        ) as ws:
            ws.send_json({"type": "message", "content": "hi"})
            msgs = _collect(ws)
    assert any(m["type"] == "done" for m in msgs)


# ── Normal message flow ───────────────────────────────────────────────────────

def test_message_streams_tokens_then_done(settings):
    graph = _SimpleGraph(tokens=["Hello", " world"], response="Hello world")
    with _ws_client(graph, settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            msgs = _collect(ws)

    tokens = [m for m in msgs if m["type"] == "token"]
    assert [t["content"] for t in tokens] == ["Hello", " world"]
    done = next(m for m in msgs if m["type"] == "done")
    assert done["agent"] == "companion"
    assert done["routing_method"] == "embedding"
    assert "confidence" in done


def test_done_message_includes_routing_metadata(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            msgs = _collect(ws)

    done = next(m for m in msgs if m["type"] == "done")
    assert set(done.keys()) >= {"type", "agent", "routing_method", "confidence"}


# ── Error handling ────────────────────────────────────────────────────────────

def test_invalid_json_returns_error(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_text("not { valid json ~~~")
            msg = ws.receive_json()
    assert msg["type"] == "error"


def test_unknown_message_type_returns_error(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "unknown_type", "content": "hi"})
            msg = ws.receive_json()
    assert msg["type"] == "error"


def test_graph_exception_returns_error_message(settings):
    with _ws_client(_ErrorGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "graph exploded" in msg["message"]


def test_second_message_while_active_returns_error(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            # The handler called _get_session on connect — mutate the live entry.
            ws_module._sessions[SESSION].active = True
            ws.send_json({"type": "message", "content": "hi"})
            msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "in progress" in msg["message"]


# ── Confirmation flow ─────────────────────────────────────────────────────────

def test_graph_pause_sends_confirmation_request(settings):
    with _ws_client(_ConfirmingGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "draft something"})
            msgs = _collect(ws, stop_on={"confirmation_request"})

    req = next(m for m in msgs if m["type"] == "confirmation_request")
    assert req["draft"] == "Draft content"
    assert req["agent"] == "companion"
    assert req["action"] == "reason"


def test_confirm_no_sends_done_without_resuming_graph(settings):
    graph = _ConfirmingGraph()
    with _ws_client(graph, settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "draft something"})
            _collect(ws, stop_on={"confirmation_request"})

            ws.send_json({"type": "confirm", "decision": "no"})
            msgs = _collect(ws)

    assert graph._calls == 1  # graph was NOT resumed
    assert any(m["type"] == "done" for m in msgs)


def test_confirm_yes_resumes_graph_and_streams(settings):
    graph = _ConfirmingGraph()
    with _ws_client(graph, settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "draft something"})
            _collect(ws, stop_on={"confirmation_request"})

            ws.send_json({"type": "confirm", "decision": "yes"})
            msgs = _collect(ws)

    assert graph._calls == 2  # graph WAS resumed
    token_content = "".join(m["content"] for m in msgs if m["type"] == "token")
    assert "Final" in token_content
    assert any(m["type"] == "done" for m in msgs)


def test_confirm_edit_patches_state_and_resumes(settings):
    graph = _ConfirmingGraph()
    with _ws_client(graph, settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "message", "content": "draft something"})
            _collect(ws, stop_on={"confirmation_request"})

            ws.send_json({"type": "confirm", "decision": "edit", "edit_content": "My edit"})
            msgs = _collect(ws)

    assert graph._calls == 2
    assert any(m["type"] == "done" for m in msgs)


def test_confirm_with_no_pending_returns_error(settings):
    with _ws_client(_SimpleGraph(), settings) as client:
        with client.websocket_connect(f"/ws/{SESSION}?token={API_KEY}") as ws:
            ws.send_json({"type": "confirm", "decision": "yes"})
            msg = ws.receive_json()
    assert msg["type"] == "error"
    assert "pending" in msg["message"].lower()


# ── Confirmation timeout (unit) ───────────────────────────────────────────────

async def test_confirmation_timeout_sends_expired_message():
    ws = MagicMock()
    ws.send_text = AsyncMock()
    graph = _SimpleGraph()
    config: dict = {"configurable": {}}

    await ws_module._confirmation_timeout(ws, SESSION, graph, config, timeout_seconds=0)

    ws.send_text.assert_called_once()
    data = json.loads(ws.send_text.call_args[0][0])
    assert data["type"] == "confirmation_expired"


async def test_confirmation_timeout_cancelled_before_firing():
    ws = MagicMock()
    ws.send_text = AsyncMock()
    graph = _SimpleGraph()
    config: dict = {"configurable": {}}

    task = asyncio.create_task(
        ws_module._confirmation_timeout(ws, SESSION, graph, config, timeout_seconds=60)
    )
    await asyncio.sleep(0)  # let the task start and suspend at asyncio.sleep(60)
    task.cancel()
    await asyncio.sleep(0)  # let cancellation propagate

    assert task.done()
    ws.send_text.assert_not_called()
