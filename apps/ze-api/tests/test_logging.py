import json
from ze_api.logging import configure_logging, get_logger, bind_context, unbind_context


def test_configure_logging_does_not_raise():
    configure_logging("DEBUG")
    configure_logging("INFO")


def test_get_logger_returns_bound_logger():
    configure_logging()
    logger = get_logger("test")
    assert logger is not None


def test_bind_context_sets_session_id(capsys):
    configure_logging()
    bind_context(session_id="sess-123")
    get_logger("test").info("hello")
    unbind_context()

    out = capsys.readouterr().out
    record = json.loads(out.strip())
    assert record["session_id"] == "sess-123"
    assert record["event"] == "hello"


def test_bind_context_sets_agent(capsys):
    configure_logging()
    bind_context(session_id="sess-456", agent="research")
    get_logger("test").info("routing")
    unbind_context()

    out = capsys.readouterr().out
    record = json.loads(out.strip())
    assert record["agent"] == "research"


def test_unbind_context_clears_fields(capsys):
    configure_logging()
    bind_context(session_id="sess-789")
    unbind_context()
    get_logger("test").info("clean")

    out = capsys.readouterr().out
    record = json.loads(out.strip())
    assert "session_id" not in record
