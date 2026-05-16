class ZeError(Exception):
    """Base exception for all Ze errors."""


# ── Routing ───────────────────────────────────────────────────────────────────

class RoutingError(ZeError):
    """Routing failed after all attempts."""


class InvalidPromptError(RoutingError):
    """Prompt is empty or invalid."""


# ── Agents ────────────────────────────────────────────────────────────────────

class AgentError(ZeError):
    """An agent failed during execution."""


class AgentTimeoutError(AgentError):
    """Agent exceeded its configured timeout."""


class UnknownAgentError(AgentError):
    """No agent registered for the requested name."""


class ToolError(AgentError):
    """A tool call within an agent failed."""


# ── Capability ────────────────────────────────────────────────────────────────

class CapabilityError(ZeError):
    """Capability gate error."""


class CapabilityConfigError(CapabilityError):
    """capabilities.yaml could not be loaded or is invalid."""


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryError(ZeError):
    """Memory store operation failed."""


# ── OpenRouter ────────────────────────────────────────────────────────────────

class OpenRouterError(ZeError):
    """OpenRouter API call failed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(OpenRouterError):
    """OpenRouter returned HTTP 429."""
