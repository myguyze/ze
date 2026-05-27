from unittest.mock import AsyncMock, MagicMock

import pytest

from ze.interface.preprocessor import TelegramInputPreprocessor
from ze.transcription.types import TranscriptionResult
from ze_core.interface.types import RawInput


@pytest.fixture
def transcription():
    client = MagicMock()
    client.transcribe = AsyncMock(
        return_value=TranscriptionResult(text="hello from voice"),
    )
    return client


async def test_text_passthrough():
    p = TelegramInputPreprocessor()
    out = await p.process(RawInput(text="hi there"), client=None)
    assert out.prompt == "hi there"
    assert out.input_modality == "text"


async def test_image_carries_bytes(transcription):
    p = TelegramInputPreprocessor(transcription_client=transcription)
    raw = RawInput(text="caption", image=b"\xff\xd8\xff", image_mime="image/jpeg")
    out = await p.process(raw, client=None)
    assert out.input_modality == "image"
    assert out.image_data == raw.image
    assert out.prompt == "caption"


async def test_voice_transcribes(transcription):
    p = TelegramInputPreprocessor(transcription_client=transcription)
    out = await p.process(RawInput(audio=b"oggbytes", audio_mime="audio/ogg"), client=None)
    assert out.input_modality == "voice"
    assert out.prompt == "hello from voice"
    transcription.transcribe.assert_awaited_once()
