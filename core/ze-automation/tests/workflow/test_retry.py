from ze_agents.errors import AgentTimeoutError, RateLimitError
from ze_automation.workflow.retry import is_transient_failure


def test_rate_limit_error_is_transient():
    assert is_transient_failure(None, RateLimitError("429", status_code=429))


def test_agent_timeout_is_transient():
    assert is_transient_failure(None, AgentTimeoutError("timed out"))


def test_timeout_message_is_transient():
    assert is_transient_failure("Request timeout after 30s")


def test_verification_failure_is_not_transient():
    assert not is_transient_failure("Verification failed: output missing key facts")


def test_empty_output_is_not_transient():
    assert not is_transient_failure("Step produced empty output")
