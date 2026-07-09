# Multimodal Input — Spec

> **Ze Core boundary:** Transport-agnostic types (`RawInput`) live in ze-core.
> `Container.invoke_raw()` maps bytes directly into `AgentState`; the graph's
> `preprocess` node handles transcription and vision captioning via `OpenRouterClient`
> (`zc-05-orchestration.md`). This spec covers **Ze application** behaviour:
> Telegram handlers and `AgentState` fields consumed by graph nodes.

## Purpose

Extend Ze's Telegram interface to accept **voice notes** and **photos** in addition
to text messages. Voice is transcribed to text before the graph runs (transparent to
all agents). Photos are carried through the graph as raw bytes and passed directly
to vision-capable agents; a lightweight vision caption is generated at the routing
step for intent classification.

Both modalities use the existing `openrouter` Python SDK and `OPENROUTER_API_KEY` —
no new credentials or HTTP clients.

---

## Responsibilities

- Detect voice and photo updates in the Telegram handler alongside the existing text
  path.
- Transcribe OGG voice notes to text via `openai/whisper-1` (chat completions with
  an `input_audio` content block) before graph invocation.
- Download photo bytes from Telegram and carry them in `AgentState` through the graph.
- Generate a vision caption at `embed_route` when an image is present and the prompt
  is empty, so the embedding router has text to work with.
- Pass image bytes to vision-capable agents as a `ChatContentImage` content block in
  the user message; fall back to the routing caption for non-vision agents.
- Store only the routing caption (not base64 bytes) in `AgentState.messages` for
  conversation history replay.

---

## Out of Scope

- Video messages, stickers, GIFs, documents, and audio files (voice notes only).
- Streaming transcription or real-time audio input.
- Group chat photo or voice handling (single-user system, already enforced).
- Whisper cost tracking in `CostTracker` — audio is billed per minute, not tokens.
  Logged via structlog; a follow-up to `17-cost-telemetry.md` will add
  `audio_seconds` support.
- Image generation or editing.
- OCR — text visible in images reaches the model only via the vision model's
  interpretation, not a dedicated OCR step.

---

## Repository Layout

```
ze/
├── telegram/
│   ├── bot.py              # add _handle_voice(), _handle_photo()
│   └── handlers.py         # register voice and photo message handlers
├── orchestration/
│   ├── state.py            # add input_modality, image_data, image_mime
│   └── nodes/
│       ├── routing.py      # add _vision_caption() helper
│       └── execution.py    # build ChatContentImage when vision_capable
├── errors.py               # add TranscriptionError, ImageDownloadError
└── container.py            # wire TranscriptionClient
config/
└── config.yaml             # add whisper + vision_caption models; vision_capable per agent
```

---

## AgentState Extensions

`ze/orchestration/state.py`

```python
class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    prompt: str
    session_id: str
    session_overrides: dict[str, str]
    input_modality: str        # "text" | "voice" | "image" — default "text"

    # ── Multimodal ─────────────────────────────────────────────────────────
    image_data: bytes | None   # raw image bytes; None for text/voice turns
    image_mime: str | None     # "image/jpeg" | "image/png" | None
    image_caption: str | None  # routing caption generated at embed_route; None until set

    # ... all existing fields unchanged ...
```

`input_modality`, `image_data`, `image_mime`, and `image_caption` are set once at
the Telegram layer and treated as read-only by all subsequent graph nodes.

---

## New Module: `ze/transcription/`

### `ze/transcription/types.py`

```python
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    text: str
```

### `ze/transcription/client.py`

Uses the existing `openrouter` SDK via `OpenRouterClient`. The SDK's
`ChatContentAudio` component (`type: "input_audio"`) carries base64 audio data
through the standard chat completions endpoint. OGG is in the SDK's supported
format list alongside mp3, wav, flac, m4a.

```python
import base64

from ze.openrouter.client import OpenRouterClient
from ze.transcription.types import TranscriptionResult


class TranscriptionClient:
    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        model: str,
        logger,
    ) -> None: ...

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str,   # e.g. "ogg"
    ) -> TranscriptionResult:
        """
        Sends a single-turn chat message with audio content to the Whisper model.
        Returns the assistant's response text as the transcription.
        """
        message = {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(audio_bytes).decode(),
                        "format": audio_format,
                    },
                }
            ],
        }
        text = await self._client.complete(
            messages=[message],
            model=self._model,
        )
        self._log.info(
            "transcription_complete",
            model=self._model,
            audio_bytes=len(audio_bytes),
            audio_format=audio_format,
        )
        return TranscriptionResult(text=text.strip())
```

On failure, `OpenRouterClient.complete()` raises `OpenRouterError` which the
Telegram handler catches and re-raises as `TranscriptionError`.

---

## Telegram Layer Changes

### New update paths in `ze/telegram/handlers.py`

Register two new aiogram message type filters alongside the existing text handler:

```python
router.message.register(handle_voice, F.voice | F.audio)
router.message.register(handle_photo, F.photo)
```

### Voice path

```
1. Verify secret_token header and chat_id (same as text path).
2. Check ActiveSessionStore — reject if already active.
3. bot.get_file(message.voice.file_id) → File object.
4. bot.download_file(file.file_path) → BytesIO.
5. invoke_raw_turn(session_id, RawInput(audio=bytes, audio_mime="audio/ogg"))
   The graph's preprocess node calls openrouter_client.transcribe() and sets
   AgentState.prompt = transcript, input_modality = "voice".
   On OpenRouterError: graph surfaces the error; bot sends generic error message.
```

### Photo path

```
1. Verify secret_token header and chat_id.
2. Check ActiveSessionStore — reject if already active.
3. photo = message.photo[-1]  # highest resolution
4. If photo.file_size > 8_388_608 (8 MB):
       send "Image is too large to process (max 8 MB)." and return.
5. bot.get_file(photo.file_id) → File object.
6. bot.download_file(file.file_path) → BytesIO.
   On failure: raise ImageDownloadError.
7. AgentState.prompt          = message.caption or ""
   AgentState.input_modality  = "image"
   AgentState.image_data      = bytes
   AgentState.image_mime      = "image/jpeg"
   AgentState.image_caption   = None   # set by embed_route
8. Proceed with normal graph invocation.
```

Telegram voice files are OGG/OPUS. Photos are always served as JPEG by Telegram's
file server regardless of the original upload format.

---

## Routing Node Change

`ze/orchestration/nodes/routing.py` (or whichever node runs `embed_route`)

The embedding router requires text. When `input_modality == "image"` and
`prompt == ""`, there is nothing to embed.

```python
async def _vision_caption(
    image_data: bytes,
    image_mime: str,
    client: OpenRouterClient,
    model: str,
) -> str:
    """
    Calls a cheap vision model to produce a one-sentence routing description.
    Result is used for embedding only; not shown to the user.
    """
    import base64
    message = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_mime};base64,{base64.b64encode(image_data).decode()}",
                    "detail": "low",
                },
            },
            {"type": "text", "text": "Describe this image in one sentence for intent classification."},
        ],
    }
    return await client.complete(messages=[message], model=model, max_tokens=80)
```

Logic in `embed_route`:

```python
if state.get("input_modality") == "image" and not state.get("prompt"):
    caption = await _vision_caption(
        state["image_data"], state["image_mime"], openrouter_client, vision_caption_model
    )
    routing_text = caption
    # store caption for history and fallback
    updates["image_caption"] = caption
else:
    routing_text = state["prompt"]
    if state.get("input_modality") == "image":
        updates["image_caption"] = state["prompt"]   # use the user's own caption
```

The caption is stored back to `AgentState.image_caption` so the execution node can
use it as a fallback without re-calling the vision model.

---

## Execution Node Change

`ze/orchestration/nodes/execution.py`

When building the user message passed to the agent, check `image_data` and the
agent's `vision_capable` config flag:

```python
def _build_user_message(state: AgentState, agent_config: dict) -> dict:
    prompt = state["prompt"] or state.get("image_caption", "")
    vision_capable = agent_config.get("vision_capable", True)

    if state.get("image_data") and vision_capable:
        import base64
        mime = state.get("image_mime", "image/jpeg")
        content: list = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(state['image_data']).decode()}",
                    "detail": "auto",
                },
            },
        ]
        if prompt:
            content.append({"type": "text", "text": prompt})
        return {"role": "user", "content": content}

    # text-only path (non-vision agent or no image)
    return {"role": "user", "content": prompt}
```

The `agent_config` dict is already available in the execution node from the loaded
`config/config.yaml` agents section.

---

## Conversation History

`AgentState.messages` stores completed turns for context. Storing raw base64 bytes
in history is prohibitive — a single 8 MB image encodes to ~10.7 MB base64, which
would bloat every subsequent graph invocation.

Resolution: when a completed image turn is accumulated into `AgentState.messages`,
the user entry is stored as:

```python
{"role": "user", "content": f"[Image] {state.get('image_caption') or ''}"}
```

The base64 bytes exist only for the current turn's `AgentContext`. They are not
written to `messages`, not persisted to Postgres checkpointer state beyond the
current turn, and not replayed in follow-up calls.

---

## Cost Tracking

Whisper calls go through `OpenRouterClient.complete()`, which already calls
`CostTracker.record()` after every completion. A row is written to `llm_cost_log`
with the `generation_id` returned by OpenRouter. `CostReconciler` then backfills
`cost_usd` via `GET /api/v1/generation?id=<id>` — the same path used for all
other agents. No schema changes, no new `CostTracker` methods required.

The only requirement is that `TranscriptionClient` sets the telemetry context
before calling `client.complete()`, so the row is attributed correctly:

```python
from ze.telemetry.context import set_agent_context, set_flow_context

async def transcribe(self, audio_bytes: bytes, audio_format: str) -> TranscriptionResult:
    set_flow_context("transcription")
    set_agent_context("whisper")
    # ... build message and call client.complete() ...
```

`token` fields in `llm_cost_log` will be zero or nominal for Whisper calls (audio
is billed per minute, not tokens). `cost_usd` from the reconciler will reflect the
actual audio-duration cost as reported by OpenRouter — no local pricing table needed.

Add the new attribution row to the table in `17-cost-telemetry.md`:

| Module | What is set |
|--------|-------------|
| `ze/transcription/client.py` — `transcribe()` | `set_flow_context("transcription")` + `set_agent_context("whisper")` |

---

## Error Types

`ze/errors.py` — add two new subclasses:

```python
class TranscriptionError(ZeError):
    """Audio file could not be transcribed by the Whisper model."""

class ImageDownloadError(ZeError):
    """Failed to download image bytes from Telegram's file server."""
```

---

## Config Changes

`config/config.yaml`:

```yaml
models:
  # ... existing entries ...
  whisper: openai/whisper-1           # openai/whisper-large-v3 for higher accuracy
  vision_caption: google/gemini-flash-1.5  # cheap model for routing captions only

agents:
  research:
    # ... existing fields ...
    vision_capable: true

  companion:
    # ... existing fields ...
    vision_capable: true

  calendar:
    # ... existing fields ...
    vision_capable: true

  email:
    # ... existing fields ...
    vision_capable: true

  workflow:
    # ... existing fields ...
    vision_capable: true
```

`vision_capable` defaults to `true` if absent. New agents should declare it
explicitly.

---

## Container / Invocation Changes

**Target shape** (when Telegram preprocessor is implemented):

1. Ze implements `TelegramInputPreprocessor(InputPreprocessor)` — downloads
   voice/photo from Telegram, runs Whisper / vision caption, returns `ProcessedInput`.
2. Register on the ze-core `Container`: `preprocessor=telegram_preprocessor`.
3. Telegram handlers call `container.invoke_raw(RawInput(...), session_id=...)` instead
   of building `AgentState` and calling `graph.ainvoke()` directly.

Until that migration lands, Ze may still transcribe in the bot layer and call
`container.invoke(prompt=..., input_modality=..., image_data=...)`.

`TranscriptionClient` (or equivalent logic inside the preprocessor) uses the
existing `OpenRouterClient` and `config["models"]["whisper"]`. No separate HTTP
client package is required.

---

## Settings

No new `.env` variables. `TranscriptionClient` receives the existing
`OpenRouterClient` instance. The `whisper` and `vision_caption` model strings are
read from `config/config.yaml` at startup.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openrouter` (existing) | `ChatContentAudio` and `ChatContentImage` content types via `chat.send_async()` |
| `aiogram` (existing) | `bot.get_file()`, `bot.download_file()`, `F.voice`, `F.photo` filters |
| `ze.openrouter.client` (existing) | All LLM calls including transcription and vision captioning |

---

## Flow Summary

```
Telegram voice update
  → download OGG bytes
  → RawInput(audio=bytes, audio_mime="audio/ogg") → invoke_raw_turn()
  → graph preprocess node:
      openrouter_client.transcribe(ogg, "ogg", model=whisper)
      AgentState.prompt = transcript, input_modality = "voice"
  → [embed_route → capability_check → execute_tool → …]

Telegram photo update
  → size check (> 8 MB → reject)
  → download JPEG bytes
  → RawInput(image=bytes, image_mime="image/jpeg") → invoke_raw_turn()
  → graph preprocess node:
      if no prompt → openrouter_client.complete([{image_url}]) → AgentState.image_caption
      else          → AgentState.image_caption = prompt
  → embed_route (routes on image_caption):
  → execute_tool:
      vision_capable? → ChatContentImage message → agent LLM call
      else            → AgentState.image_caption as plain text prompt
  → write_memory:
      messages += {"role": "user", "content": "[Image] <caption>"}
```

---

## Testing

- `OpenRouterClient.transcribe()`: see `ze-core/tests/openrouter/test_transcribe.py`.
  Asserts `input_audio` content block, base64 encoding, format normalisation, model
  passthrough, telemetry context, and duration.
- `preprocess` node (audio path): mock `openrouter_client.transcribe`; assert state
  update sets `prompt`, `input_modality="voice"`, clears `audio_data`/`audio_mime`.
- `ZeBot.handle_voice()`: mock `bot.download_file`; assert `RawInput(audio=bytes,
  audio_mime="audio/ogg")` is passed to `invoke_raw_turn`.
- `ZeBot._handle_photo()`: assert size guard rejects files > 8 MB; assert
  `image_data`, `image_mime`, and `input_modality` are set correctly.
- `_vision_caption()`: mock `OpenRouterClient.complete`; assert the message contains
  an `image_url` block with a valid `data:image/jpeg;base64,…` URL.
- `_build_user_message()` with `vision_capable: true`: assert multipart content list
  with `image_url` block and optional text block.
- `_build_user_message()` with `vision_capable: false`: assert plain text prompt
  using `image_caption`.
- History accumulation: assert that image turns produce `[Image] <caption>` in
  `AgentState.messages`, not base64 bytes.

---

## Open Questions

All resolved.

- **Whisper cost tracking**: Resolved — Whisper calls go through
  `OpenRouterClient.complete()`, which already invokes `CostTracker.record()`.
  `CostReconciler` backfills `cost_usd` via `generation_id` exactly as it does for
  all other agents. `TranscriptionClient` sets `flow_type="transcription"` and
  `agent="whisper"` via telemetry context before each call. No schema or tracker
  changes required. See the Cost Tracking section above.
- **Image size limit**: Reject at the Telegram layer if `photo.file_size > 8_388_608`
  (8 MB). If `file_size` is absent, proceed and let any API error surface as
  `ImageDownloadError`.
- **History with images**: Base64 bytes are turn-scoped only. History stores
  `[Image] <caption>` as the user message for replay.
- **Vision fallback**: `vision_capable` flag per agent in `config/config.yaml`.
  All five current agents are `true`. Execution node substitutes `image_caption`
  for non-vision agents.
