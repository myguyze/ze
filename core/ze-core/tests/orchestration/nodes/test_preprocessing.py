from unittest.mock import AsyncMock

from ze_core.orchestration.nodes.preprocessing import preprocess


def _config(settings: dict, client=None) -> dict:
    return {
        "configurable": {
            "openrouter_client": client or AsyncMock(),
            "settings": settings,
        }
    }


class TestCapabilityKeysBypassResolver:
    """models.default must never influence transcription or vision captioning —
    both call sites read models.whisper / models.vision_caption directly."""

    async def test_transcription_uses_models_whisper_regardless_of_default(self):
        client = AsyncMock()
        client.transcribe = AsyncMock(return_value="transcribed text")
        settings = {
            "models": {
                "default": "fleet-default-model",
                "overrides": {},
                "whisper": "pinned-whisper-model",
            }
        }
        state = {"audio_data": b"raw-bytes", "audio_mime": "audio/ogg"}

        await preprocess(state, _config(settings, client=client))

        assert client.transcribe.call_args.kwargs["model"] == "pinned-whisper-model"

    async def test_vision_caption_uses_models_vision_caption_regardless_of_default(self):
        client = AsyncMock()
        client.complete = AsyncMock(return_value="a caption")
        settings = {
            "models": {
                "default": "fleet-default-model",
                "overrides": {},
                "vision_caption": "pinned-vision-model",
            }
        }
        state = {"image_data": b"raw-bytes", "image_mime": "image/jpeg", "prompt": None}

        await preprocess(state, _config(settings, client=client))

        assert client.complete.call_args.kwargs["model"] == "pinned-vision-model"

    async def test_transcription_falls_back_to_declared_constant_not_default(self):
        client = AsyncMock()
        client.transcribe = AsyncMock(return_value="transcribed text")
        settings = {"models": {"default": "fleet-default-model", "overrides": {}}}
        state = {"audio_data": b"raw-bytes", "audio_mime": "audio/ogg"}

        await preprocess(state, _config(settings, client=client))

        from ze_agents.defaults import MODEL_WHISPER

        assert client.transcribe.call_args.kwargs["model"] == MODEL_WHISPER
