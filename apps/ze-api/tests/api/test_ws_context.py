import json

import pytest

from ze_logging import configure_logging, get_logger
from ze_api.api.websocket.context import bound_turn_context


@pytest.fixture(autouse=True)
def _fresh_logging():
    configure_logging()
    yield
    configure_logging()


def test_bound_turn_context_binds_and_clears(capsys):
    with bound_turn_context("thread-abc", agent="research"):
        get_logger("test").info("during_turn")
    get_logger("test").info("after_turn")

    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert lines[0]["session_id"] == "thread-abc"
    assert lines[0]["agent"] == "research"
    assert "session_id" not in lines[1]
