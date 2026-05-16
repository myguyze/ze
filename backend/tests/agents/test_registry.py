import pytest

from ze.agents.registry import (
    _instances,
    _registry,
    get_agent,
    register,
    register_instance,
    registered_names,
)
from ze.errors import UnknownAgentError
from ze.logging import configure_logging


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture(autouse=True)
def clean_instances():
    """Isolate instance registry mutations per test."""
    before = dict(_instances)
    yield
    _instances.clear()
    _instances.update(before)


# ── @register ─────────────────────────────────────────────────────────────────

def test_register_decorator_adds_to_registry():
    @register
    class FakeAgent:
        name = "fake_test_agent"

    assert "fake_test_agent" in _registry
    assert _registry["fake_test_agent"] is FakeAgent


def test_register_returns_class_unchanged():
    @register
    class AnotherFake:
        name = "another_fake"
        value = 42

    assert AnotherFake.value == 42


# ── register_instance / get_agent ─────────────────────────────────────────────

def test_register_and_get_instance():
    sentinel = object()
    register_instance("my_agent", sentinel)
    assert get_agent("my_agent") is sentinel


def test_get_agent_raises_for_unknown():
    with pytest.raises(UnknownAgentError, match="no_such_agent"):
        get_agent("no_such_agent")


def test_register_instance_overwrites_previous():
    obj1 = object()
    obj2 = object()
    register_instance("overwrite_me", obj1)
    register_instance("overwrite_me", obj2)
    assert get_agent("overwrite_me") is obj2


# ── registered_names ──────────────────────────────────────────────────────────

def test_registered_names_includes_known_agents():
    # research and companion agents are imported at module level via @register
    import ze.agents.research.agent  # noqa: F401
    import ze.agents.companion.agent  # noqa: F401
    names = registered_names()
    assert "research" in names
    assert "companion" in names
