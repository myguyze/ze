import asyncio
import json
from dataclasses import asdict, dataclass

from fastapi import WebSocket, WebSocketDisconnect
from sentence_transformers import SentenceTransformer

from ze.api.schemas import (
    ConfirmationExpiredMessage,
    ConfirmationRequest,
    ConfirmMessage,
    DoneMessage,
    ErrorMessage,
    TokenMessage,
    UserMessage,
    WsClientMessage,
)
from ze.capability.gate import CapabilityGate
from ze.logging import bind_context, get_logger, unbind_context
from ze.memory.store import MemoryStore
from ze.openrouter.client import OpenRouterClient
from ze.routing.router import EmbeddingRouter
from ze.settings import Settings

log = get_logger(__name__)

# ── Per-session in-process state ──────────────────────────────────────────────
# LangGraph owns graph state (survives restarts via Postgres).
# This dict only tracks runtime coordination: active flag, confirm task.

@dataclass
class _SessionState:
    active: bool = False
    confirm_task: asyncio.Task | None = None
    pending_config: dict | None = None


_sessions: dict[str, _SessionState] = {}


def _get_session(session_id: str) -> _SessionState:
    if session_id not in _sessions:
        _sessions[session_id] = _SessionState()
    return _sessions[session_id]


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(websocket: WebSocket, api_key: str) -> bool:
    auth = websocket.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] == api_key
    # Also allow via query param for clients that can't set headers on WS upgrade
    token = websocket.query_params.get("token", "")
    return token == api_key


# ── Send helpers ──────────────────────────────────────────────────────────────

async def _send(ws: WebSocket, msg) -> None:
    await ws.send_text(msg.model_dump_json())


# ── Config builder ────────────────────────────────────────────────────────────

def _make_graph_config(
    session_id: str,
    token_queue: asyncio.Queue,
    router: EmbeddingRouter,
    capability_gate: CapabilityGate,
    memory_store: MemoryStore,
    openrouter_client: OpenRouterClient,
    embedder: SentenceTransformer,
    settings: Settings,
) -> dict:
    return {
        "configurable": {
            "thread_id": session_id,
            "token_queue": token_queue,
            "router": router,
            "capability_gate": capability_gate,
            "memory_store": memory_store,
            "openrouter_client": openrouter_client,
            "embedder": embedder,
            "settings": settings,
        }
    }


def _make_initial_state(prompt: str, session_id: str) -> dict:
    return {
        "prompt": prompt,
        "session_id": session_id,
        "session_overrides": {},
        "envelope": None,
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
        "subtask_results": [],
        "pending_confirmation": False,
        "final_response": None,
        "error": None,
    }


# ── Token consumer ────────────────────────────────────────────────────────────

async def _consume_tokens(ws: WebSocket, queue: asyncio.Queue) -> None:
    while True:
        token = await queue.get()
        if token is None:
            break
        try:
            await _send(ws, TokenMessage(content=token))
        except Exception:
            # WebSocket closed mid-stream — drain remaining tokens silently
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            break


# ── Confirmation timeout ──────────────────────────────────────────────────────

async def _confirmation_timeout(
    ws: WebSocket,
    session_id: str,
    graph,
    config: dict,
    timeout_seconds: int,
) -> None:
    try:
        await asyncio.sleep(timeout_seconds)
        await graph.aupdate_state(config, {"error": "confirmation_expired"})
        try:
            await _send(ws, ConfirmationExpiredMessage())
        except Exception:
            pass
        log.info("confirmation_expired", session_id=session_id)
    except asyncio.CancelledError:
        pass  # normal — user responded in time


# ── Graph runner ──────────────────────────────────────────────────────────────

async def _run_graph(
    ws: WebSocket,
    session_id: str,
    prompt: str,
    graph,
    config: dict,
) -> None:
    sess = _get_session(session_id)
    token_queue: asyncio.Queue[str | None] = asyncio.Queue()
    config["configurable"]["token_queue"] = token_queue

    input_state = _make_initial_state(prompt, session_id)
    graph_task = asyncio.create_task(graph.ainvoke(input_state, config))
    consumer_task = asyncio.create_task(_consume_tokens(ws, token_queue))

    try:
        final_state = await graph_task
    except Exception as exc:
        log.exception("graph_error", session_id=session_id, error=str(exc))
        token_queue.put_nowait(None)  # unblock consumer
        await consumer_task
        await _send(ws, ErrorMessage(message=str(exc)))
        sess.active = False
        return

    await consumer_task

    # Detect interrupt (confirmation needed)
    graph_state = await graph.aget_state(config)
    if graph_state.next:
        result = final_state.get("agent_result")
        envelope = final_state.get("envelope")
        draft = result.response if result else ""
        agent = envelope.primary_agent if envelope else ""
        action = (envelope.subtasks[0].intent if envelope and envelope.subtasks else "")

        await _send(ws, ConfirmationRequest(draft=draft, agent=agent, action=action))

        sess.pending_config = config
        sess.confirm_task = asyncio.create_task(
            _confirmation_timeout(ws, session_id, graph, config, 900)
        )
        sess.active = False
        log.info("awaiting_confirmation", session_id=session_id, agent=agent)
    else:
        envelope = final_state.get("envelope")
        await _send(ws, DoneMessage(
            agent=envelope.primary_agent if envelope else "",
            routing_method=envelope.routing_method if envelope else "embedding",
            confidence=envelope.confidence if envelope else None,
        ))
        sess.active = False
        log.info("graph_complete", session_id=session_id)


# ── Confirm handler ───────────────────────────────────────────────────────────

async def _handle_confirm(
    ws: WebSocket,
    session_id: str,
    msg: ConfirmMessage,
    graph,
) -> None:
    sess = _get_session(session_id)

    if sess.confirm_task:
        sess.confirm_task.cancel()
        sess.confirm_task = None

    config = sess.pending_config
    if config is None:
        await _send(ws, ErrorMessage(message="No pending confirmation."))
        return

    sess.pending_config = None

    if msg.decision == "no":
        await _send(ws, DoneMessage(
            agent="",
            routing_method="embedding",
            confidence=None,
        ))
        return

    # "yes" or "edit": resume the graph
    resume_input = None
    if msg.decision == "edit" and msg.edit_content is not None:
        # Patch the state with edited content and re-run from current node
        await graph.aupdate_state(
            config,
            {"agent_result": None, "prompt": msg.edit_content},
        )

    sess.active = True
    token_queue: asyncio.Queue[str | None] = asyncio.Queue()
    config["configurable"]["token_queue"] = token_queue

    graph_task = asyncio.create_task(graph.ainvoke(resume_input, config))
    consumer_task = asyncio.create_task(_consume_tokens(ws, token_queue))

    try:
        final_state = await graph_task
    except Exception as exc:
        token_queue.put_nowait(None)
        await consumer_task
        await _send(ws, ErrorMessage(message=str(exc)))
        sess.active = False
        return

    await consumer_task

    envelope = final_state.get("envelope")
    await _send(ws, DoneMessage(
        agent=envelope.primary_agent if envelope else "",
        routing_method=envelope.routing_method if envelope else "embedding",
        confidence=envelope.confidence if envelope else None,
    ))
    sess.active = False


# ── WebSocket endpoint ────────────────────────────────────────────────────────

async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    # Dependencies injected via app.state in the handler
) -> None:
    from ze.api.dependencies import (
        get_capability_gate,
        get_embedder,
        get_graph,
        get_memory_store,
        get_openrouter_client,
        get_router,
        get_settings,
    )

    settings = get_settings()

    if not _check_auth(websocket, settings.ze_api_key):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    bind_context(session_id=session_id)

    router = get_router(websocket)
    capability_gate = get_capability_gate(websocket)
    memory_store = get_memory_store(websocket)
    openrouter_client = get_openrouter_client(websocket)
    embedder = get_embedder(websocket)
    graph = get_graph(websocket)

    config = _make_graph_config(
        session_id=session_id,
        token_queue=asyncio.Queue(),  # placeholder; replaced per-invocation
        router=router,
        capability_gate=capability_gate,
        memory_store=memory_store,
        openrouter_client=openrouter_client,
        embedder=embedder,
        settings=settings,
    )

    log.info("ws_connected", session_id=session_id)
    sess = _get_session(session_id)

    try:
        async for raw in websocket.iter_text():
            try:
                data = json.loads(raw)
                from pydantic import TypeAdapter
                adapter = TypeAdapter(WsClientMessage)
                msg = adapter.validate_python(data)
            except Exception as exc:
                await _send(websocket, ErrorMessage(message=f"Invalid message: {exc}"))
                continue

            if isinstance(msg, UserMessage):
                if sess.active:
                    await _send(websocket, ErrorMessage(message="A task is already in progress."))
                    continue
                sess.active = True
                # Run graph (sets sess.active = False when done)
                await _run_graph(websocket, session_id, msg.content, graph, dict(config))

            elif isinstance(msg, ConfirmMessage):
                await _handle_confirm(websocket, session_id, msg, graph)

    except WebSocketDisconnect:
        log.info("ws_disconnected", session_id=session_id)
    except Exception as exc:
        log.exception("ws_error", session_id=session_id, error=str(exc))
    finally:
        unbind_context()
        if session_id in _sessions:
            s = _sessions[session_id]
            if s.confirm_task:
                s.confirm_task.cancel()
