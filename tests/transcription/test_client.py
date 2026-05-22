import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze.transcription.client import TranscriptionClient
from ze.transcription.types import TranscriptionResult


def make_client(response: str = "hello world") -> TranscriptionClient:
    openrouter = AsyncMock()
    openrouter.complete = AsyncMock(return_value=response)
    logger = MagicMock()
    return TranscriptionClient(
        openrouter_client=openrouter,
        model="openai/whisper-1",
        logger=logger,
    )


async def test_transcribe_returns_result():
    client = make_client("transcribed text")
    result = await client.transcribe(b"audio data", "ogg")
    assert isinstance(result, TranscriptionResult)
    assert result.text == "transcribed text"


async def test_transcribe_strips_whitespace():
    client = make_client("  hello  ")
    result = await client.transcribe(b"audio", "ogg")
    assert result.text == "hello"


async def test_transcribe_sends_input_audio_block():
    captured: list[list] = []

    openrouter = AsyncMock()
    async def _complete(messages, **kwargs):
        captured.append(messages)
        return "ok"
    openrouter.complete = _complete

    client = TranscriptionClient(
        openrouter_client=openrouter,
        model="openai/whisper-1",
        logger=MagicMock(),
    )
    audio = b"fake ogg bytes"
    await client.transcribe(audio, "ogg")

    assert len(captured) == 1
    msg = captured[0][0]
    assert msg["role"] == "user"
    block = msg["content"][0]
    assert block["type"] == "input_audio"
    assert block["input_audio"]["format"] == "ogg"
    assert block["input_audio"]["data"] == base64.b64encode(audio).decode()


async def test_transcribe_sets_telemetry_context():
    from ze.telemetry.context import get_cost_context

    openrouter = AsyncMock()
    openrouter.complete = AsyncMock(return_value="ok")

    ctx_during: list = []
    original_complete = openrouter.complete

    async def _capture(**kwargs):
        ctx_during.append(get_cost_context())
        return "ok"

    openrouter.complete = _capture

    client = TranscriptionClient(
        openrouter_client=openrouter,
        model="openai/whisper-1",
        logger=MagicMock(),
    )
    await client.transcribe(b"audio", "ogg")

    assert ctx_during
    assert ctx_during[0].flow_type == "transcription"
    assert ctx_during[0].agent == "whisper"


async def test_transcribe_uses_configured_model():
    captured_models: list[str] = []

    openrouter = AsyncMock()
    async def _complete(messages, model=None, **kwargs):
        captured_models.append(model)
        return "ok"
    openrouter.complete = _complete

    client = TranscriptionClient(
        openrouter_client=openrouter,
        model="openai/whisper-large-v3",
        logger=MagicMock(),
    )
    await client.transcribe(b"audio", "ogg")

    assert captured_models[0] == "openai/whisper-large-v3"


async def test_transcribe_passes_duration_as_audio_seconds():
    captured: list[dict] = []

    openrouter = AsyncMock()
    async def _complete(messages, **kwargs):
        captured.append(kwargs)
        return "ok"
    openrouter.complete = _complete

    client = TranscriptionClient(
        openrouter_client=openrouter,
        model="openai/whisper-1",
        logger=MagicMock(),
    )
    await client.transcribe(b"audio", "ogg", duration_seconds=12.5)

    assert captured[0]["audio_seconds"] == 12.5


async def test_transcribe_passes_none_when_no_duration():
    captured: list[dict] = []

    openrouter = AsyncMock()
    async def _complete(messages, **kwargs):
        captured.append(kwargs)
        return "ok"
    openrouter.complete = _complete

    client = TranscriptionClient(
        openrouter_client=openrouter,
        model="openai/whisper-1",
        logger=MagicMock(),
    )
    await client.transcribe(b"audio", "ogg")

    assert captured[0].get("audio_seconds") is None
