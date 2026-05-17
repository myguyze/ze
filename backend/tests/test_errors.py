from ze.errors import (
    ZeError,
    RoutingError, InvalidPromptError,
    AgentError, AgentTimeoutError, UnknownAgentError, ToolError,
    CapabilityError, CapabilityConfigError,
    MemoryError,
    OpenRouterError, RateLimitError,
)


def test_hierarchy_routing():
    assert issubclass(InvalidPromptError, RoutingError)
    assert issubclass(RoutingError, ZeError)


def test_hierarchy_agent():
    assert issubclass(AgentTimeoutError, AgentError)
    assert issubclass(UnknownAgentError, AgentError)
    assert issubclass(ToolError, AgentError)
    assert issubclass(AgentError, ZeError)


def test_hierarchy_capability():
    assert issubclass(CapabilityConfigError, CapabilityError)
    assert issubclass(CapabilityError, ZeError)


def test_hierarchy_memory():
    assert issubclass(MemoryError, ZeError)


def test_hierarchy_openrouter():
    assert issubclass(RateLimitError, OpenRouterError)
    assert issubclass(OpenRouterError, ZeError)


def test_openrouter_error_carries_status_code():
    err = OpenRouterError("bad gateway", status_code=502)
    assert err.status_code == 502
    assert str(err) == "bad gateway"


def test_openrouter_error_status_code_optional():
    err = OpenRouterError("unknown")
    assert err.status_code is None


def test_all_are_catchable_as_ze_error():
    errors = [
        InvalidPromptError("empty"),
        AgentTimeoutError("timed out"),
        UnknownAgentError("no agent"),
        ToolError("tool failed"),
        CapabilityConfigError("bad yaml"),
        MemoryError("db error"),
        RateLimitError("429", status_code=429),
    ]
    for err in errors:
        assert isinstance(err, ZeError)
