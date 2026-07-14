from __future__ import annotations

from ze_agents.errors import AgentTimeoutError, RateLimitError

STEP_MAX_ATTEMPTS: int = 3
RETRY_DELAY_SECONDS: float = 2.0

_TRANSIENT_MARKERS = (
    "timeout",
    "timed out",
    "rate limit",
    "429",
    "502",
    "503",
    "504",
)


def is_transient_failure(
    error: str | None, exc: BaseException | None = None
) -> bool:
    if isinstance(exc, (RateLimitError, AgentTimeoutError)):
        return True
    if error is None:
        return False
    lower = error.lower()
    return any(marker in lower for marker in _TRANSIENT_MARKERS)
