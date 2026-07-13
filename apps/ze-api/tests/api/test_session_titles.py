from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from ze_api.api.websocket.session_titles import _title_generator


def _container(config: dict) -> SimpleNamespace:
    settings = SimpleNamespace(config=config)
    return SimpleNamespace(settings=settings, openrouter_client=MagicMock())


class TestTitleGenerator:
    def test_uses_declared_default_when_no_override(self):
        container = _container(
            {"models": {"default": "fleet-default", "overrides": {}}}
        )
        generator = _title_generator(container)
        assert generator._model == "anthropic/claude-haiku-4-5"

    def test_override_pins_session_title_model(self):
        container = _container(
            {
                "models": {
                    "default": "fleet-default",
                    "overrides": {"session_title": "pinned-model"},
                }
            }
        )
        generator = _title_generator(container)
        assert generator._model == "pinned-model"
