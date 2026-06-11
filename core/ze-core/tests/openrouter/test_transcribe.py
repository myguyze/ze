"""Tests for OpenRouterClient.transcribe()."""
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_core.openrouter.client import OpenRouterClient


@pytest.fixture
def client():
    with patch("ze_core.openrouter.client.OpenRouter", return_value=MagicMock()):
        c = OpenRouterClient(api_key="test-key", base_url="https://openrouter.ai/api/v1")
        c.complete = AsyncMock(return_value="transcribed text")
        return c


async def test_transcribe_returns_stripped_text(client):
    client.complete = AsyncMock(return_value="  hello world  ")
    result = await client.transcribe(b"audio", "ogg", model="openai/whisper-1")
    assert result == "hello world"


async def test_transcribe_sends_input_audio_block(client):
    captured: list[list] = []

    async def _complete(messages, **kwargs):
        captured.append(messages)
        return "ok"

    client.complete = _complete
    audio = b"fake ogg bytes"
    await client.transcribe(audio, "ogg", model="openai/whisper-1")

    assert len(captured) == 1
    msg = captured[0][0]
    assert msg["role"] == "user"
    block = msg["content"][0]
    assert block["type"] == "input_audio"
    assert block["input_audio"]["format"] == "ogg"
    assert block["input_audio"]["data"] == base64.b64encode(audio).decode()


async def test_transcribe_passes_duration_as_audio_seconds(client):
    captured: list[dict] = []

    async def _complete(messages, **kwargs):
        captured.append(kwargs)
        return "ok"

    client.complete = _complete
    await client.transcribe(b"audio", "ogg", model="openai/whisper-1", duration_seconds=12.5)

    assert captured[0]["audio_seconds"] == 12.5


async def test_transcribe_passes_none_when_no_duration(client):
    captured: list[dict] = []

    async def _complete(messages, **kwargs):
        captured.append(kwargs)
        return "ok"

    client.complete = _complete
    await client.transcribe(b"audio", "ogg", model="openai/whisper-1")

    assert captured[0].get("audio_seconds") is None


async def test_transcribe_normalises_mime_format(client):
    """audio/ogg; codecs=opus → ogg."""
    captured: list[list] = []

    async def _complete(messages, **kwargs):
        captured.append(messages)
        return "ok"

    client.complete = _complete
    await client.transcribe(b"audio", "audio/ogg; codecs=opus", model="openai/whisper-1")

    block = captured[0][0]["content"][0]
    assert block["input_audio"]["format"] == "ogg"


async def test_transcribe_uses_configured_model(client):
    captured_kwargs: list[dict] = []

    async def _complete(messages, **kwargs):
        captured_kwargs.append(kwargs)
        return "ok"

    client.complete = _complete
    await client.transcribe(b"audio", "ogg", model="openai/whisper-large-v3")

    assert captured_kwargs[0]["model"] == "openai/whisper-large-v3"
