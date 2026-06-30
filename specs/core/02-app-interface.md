> ⚠️ **Status: Stale** — Written pre-split (Phases 1–20). References `ze_core/...` paths that no longer exist. See the [package specs below](../README.md#ze-core-specs-core) for current documentation.

---

# Ze Core — AppInterface — Spec

## Purpose

Define the bidirectional interface between Ze Core and the user. `AppInterface` is
the sole abstraction through which the framework communicates with the person running
the application. It is transport-agnostic: Ze implements it with Telegram, another
application implements it with Slack, a CLI, or a web API.

Everything that involves the user goes through `AppInterface`. Nothing in the
framework imports Telegram, aiogram, Slack SDKs, or any other transport library.

## Responsibilities

- `send()` — deliver a response to the user after an agent run completes.
- `confirm()` — pause execution, present a confirmation request, and return the
  user's decision. Used by the capability gate and goal verification gates.
- `push()` — deliver a proactive notification the user did not request (briefings,
  reminders, alerts, insights).
- Input normalisation is **not** part of `AppInterface`. Transport adapters build
  `RawInput` and call `Container.invoke_raw()`, or call `Container.invoke()` directly
  when input is already text (see Input preprocessing below).

Message ingestion (`receive()`) is intentionally absent from this Protocol. The
transport layer (Telegram webhook handler, CLI input loop) normalises user input
and invokes the graph via `Container.invoke()` or `Container.invoke_raw()`.
Ze Core does not poll for messages.

## Out of Scope

- Does not route messages to agents (that is the routing primitive's job).
- Does not evaluate capability modes (that is the gate's job).
- Does not send messages to external contacts or third parties (that is `Channel`'s
  job — see `zc-04-channels.md`).
- Does not authenticate the user. Single-user applications have no login flow.
- Does not transcribe audio or caption images — those LLM calls happen inside the
  graph's `preprocess` node via `OpenRouterClient` (see `zc-05-orchestration.md`).

---

## Protocol

`ze_core/interface/base.py`

```python
class AppInterface(Protocol):
    confirmation_style: ClassVar[Literal["inline", "async"]]
    """
    Declares how this interface handles confirmation requests.

    "inline"  — interface implements confirm() as a blocking call.
                The framework awaits it directly; the graph continues
                in the same invocation. Suitable for CLI, tests.

    "async"   — interface implements send_confirmation() as a one-way send.
                The framework pauses the graph via LangGraph checkpoint and
                resumes it when the external callback arrives. Suitable for
                Telegram, Slack, and any webhook-based transport.
    """

    async def send(self, message: OutboundMessage) -> None:
        """Deliver a response to the user."""

    async def push(self, notification: Notification) -> None:
        """Deliver a proactive notification. Must not raise — swallow and log errors."""

    # ── Confirmation — implement one of the two below based on confirmation_style ──

    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse:
        """
        Required when confirmation_style == "inline".

        Block until the user responds and return their decision. The graph
        continues in the same invocation immediately after this returns.
        Timeout must be enforced by the implementation; return
        ConfirmationResponse(approved=False, timed_out=True) on expiry.
        """
        raise NotImplementedError("inline interfaces must implement confirm()")

    async def send_confirmation(self, request: ConfirmationRequest) -> None:
        """
        Required when confirmation_style == "async".

        One-way send — deliver the confirmation UI (e.g. Telegram inline keyboard)
        without waiting for a response. The graph pauses after this call and resumes
        when the transport adapter's callback handler writes the decision into
        AgentState and calls graph.ainvoke(None, config) with the same thread_id.
        """
        raise NotImplementedError("async interfaces must implement send_confirmation()")
```

---

## Input Preprocessing

Multimodal transports pass raw bytes (audio, images) to the graph via `RawInput`.
All LLM-based pre-processing — transcription and vision captioning — happens inside
the graph's `preprocess` node via `OpenRouterClient` (see `zc-05-orchestration.md`).

`Container.invoke_raw()` maps `RawInput` fields directly to `AgentState`:
- `audio` bytes → `audio_data` / `audio_mime` in graph state
- `image` bytes → `image_data` / `image_mime` in graph state
- `text` → `prompt`

No application-level preprocessor is needed. Transport adapters are responsible only
for downloading bytes from transport-specific sources (e.g. Telegram CDN) before
calling `invoke_raw()`. All LLM calls stay inside the graph boundary.

---

## Types

`ze_core/interface/types.py`

```python
@dataclass
class RawInput:
    """Unprocessed input from any transport layer."""
    text: str | None = None
    audio: bytes | None = None
    audio_mime: str | None = None   # e.g. "audio/ogg; codecs=opus"
    image: bytes | None = None
    image_mime: str | None = None   # e.g. "image/jpeg"


@dataclass
class ProcessedInput:
    """Normalised input ready for graph invocation."""
    prompt: str
    input_modality: str = "text"    # "text" | "voice" | "image"
    image_data: bytes | None = None
    image_mime: str | None = None


@dataclass
class OutboundMessage:
    content: str
    format: str = "text"    # "text" | "markdown"

@dataclass
class ConfirmationRequest:
    content: str                  # what is being confirmed — shown to the user
    options: list[str]            # choices presented, e.g. ["Approve", "Reject"]
    editable: bool = False        # whether the user can supply a free-text edit
    timeout_seconds: int | None = None  # None → use CONFIRM_TIMEOUT_SECONDS setting

@dataclass
class ConfirmationResponse:
    approved: bool
    edited_content: str | None = None  # populated only when editable=True and user edited
    timed_out: bool = False            # True when the confirmation window expired

@dataclass
class Action:
    label: str
    payload: str   # opaque string returned by the transport on tap

@dataclass
class Notification:
    content: str
    format: str = "text"    # "text" | "markdown"
    urgency: str = "normal" # "normal" | "high"
    actions: list[Action] = field(default_factory=list)

@dataclass
class InvokeResult:
    """Return value from Container.invoke(), invoke_raw(), and resume()."""
    session_id: str
    response: str | None = None
    confirmation_pending: bool = False
    error: str | None = None
```

---

## `confirm()` — Execution Model

The framework branches in the `await_confirmation` node based on
`interface.confirmation_style`. Two patterns exist; interfaces declare which one
they use via the `confirmation_style` class variable.

### Pattern 1 — Inline (`confirmation_style = "inline"`)

The interface implements `confirm()` as a blocking call. The framework awaits it
directly; the graph continues in the same invocation. No checkpoint is needed.

```python
class CLIInterface(AppInterface):
    confirmation_style = "inline"

    async def confirm(self, request: ConfirmationRequest) -> ConfirmationResponse:
        print(request.content)
        for i, opt in enumerate(request.options, 1):
            print(f"  {i}. {opt}")
        raw = input("> ").strip()
        approved = raw == "1" or raw.lower() in ("y", "yes", "approve")
        return ConfirmationResponse(approved=approved)
```

The CLI adapter ships with Ze Core and is the reference implementation. Suitable
for development, testing, and non-interactive scripts.

### Pattern 2 — Async (`confirmation_style = "async"`)

Webhook-based interfaces cannot block. Instead, the framework uses LangGraph's
checkpoint mechanism.

```python
class TelegramInterface(AppInterface):
    confirmation_style = "async"

    async def send_confirmation(self, request: ConfirmationRequest) -> None:
        """One-way send — deliver the confirmation UI (e.g. inline keyboard)."""
        ...
```

Flow:

1. The capability gate returns `GateDecision.AWAIT_CONFIRMATION`.
2. The orchestration graph routes to the `await_confirmation` node.
3. `await_confirmation` calls `interface.send_confirmation(request)` — delivers
   the confirmation UI to the user (e.g. Telegram inline keyboard).
4. The graph run ends. The process is free to handle other requests.
5. The user responds via a new HTTP request (Telegram callback).
6. The transport adapter's callback handler writes the decision into `AgentState`
   and calls `graph.ainvoke(None, config)` with the same `thread_id`.
7. The graph resumes from the checkpoint with the user's decision in state.

### `await_confirmation` node — branching logic

```python
async def await_confirmation(state: AgentState, config: RunnableConfig) -> dict:
    interface: AppInterface = config["configurable"]["interface"]
    request = _build_confirmation_request(state)

    if interface.confirmation_style == "inline":
        response = await interface.confirm(request)
        return {"confirmation_response": response}
    else:
        await interface.send_confirmation(request)
        # Graph pauses here; resumed by the transport callback handler.
        return {}
```

### Startup validation

The container validates that each registered interface implements the method
required by its declared `confirmation_style`:

| `confirmation_style` | Required method | Missing → |
|---|---|---|
| `"inline"` | `confirm()` | `InterfaceConfigError` at startup |
| `"async"` | `send_confirmation()` | `InterfaceConfigError` at startup |

---

## CLI Adapter

`ze_core/interface/cli.py`

Ze Core ships a CLI adapter as the minimum viable interface. It allows developers
to test agents without running a bot or web server.

```
$ ze-cli
You: what's on my calendar tomorrow?
[research] Searching...
Ze: You have two events tomorrow: ...

You: schedule a meeting with João at 3pm
Ze: Create event "Meeting with João" on Thursday at 3pm?
  1. Approve
  2. Reject
> 1
Ze: Done. Event created.
```

The CLI adapter:
- Reads messages from stdin in a loop.
- Sends responses to stdout.
- Implements `confirm()` synchronously (Pattern 1 above).
- Implements `push()` by printing to stdout with a `[notification]` prefix.
- Exits cleanly on EOF or `Ctrl-C`.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.errors` | `InterfaceError` base class |
| `ze_core.orchestration.state` | `AgentState` — read/written by `await_confirmation` node |
| `ze_core.container` | `invoke_raw()` — calls `InputPreprocessor` when registered |

---

## Related Specs

| Spec | Relationship |
|---|---|
| `zc-07-container.md` | `invoke()`, `invoke_raw()`, `resume()` — graph entry points |
| `phases/19-multimodal-input.md` | Ze Telegram handlers + Whisper/vision (application layer) |
| `zc-05-orchestration.md` | `AgentState.input_modality`, `image_data`, vision caption in `embed_route` |

---

## Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| `send()` raises (network error, rate limit) | Log and swallow — never propagate to the graph |
| `push()` raises | Log and swallow — proactive failures must not crash the scheduler |
| `confirm()` times out (synchronous pattern) | Return `ConfirmationResponse(approved=False, timed_out=True)` |
| `confirm()` called on a webhook interface | Raise `NotImplementedError` with a clear message pointing to `send_confirmation()` |

---

## Errors / Edge Cases (continued)

| Condition | Behaviour |
|---|---|
| `confirmation_style` missing from interface class | `InterfaceConfigError` at startup |
| `confirmation_style == "inline"` but `confirm()` not overridden | `InterfaceConfigError` at startup |
| `confirmation_style == "async"` but `send_confirmation()` not overridden | `InterfaceConfigError` at startup |
| `confirmation_style` value other than `"inline"` or `"async"` | `InterfaceConfigError` at startup |
