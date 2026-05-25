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


class UnknownToolError(ToolError):
    """No tool registered for the requested name."""


class ToolBlockedError(ToolError):
    """Tool call rejected by the capability gate."""


class AgentConfigError(AgentError):
    """Agent or tool misconfiguration detected at startup."""


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


# ── Workflow ───────────────────────────────────────────────────────────────────

class WorkflowError(ZeError):
    """Base class for workflow errors."""


class WorkflowPlanError(WorkflowError):
    """Planner failed to produce a valid workflow plan."""


class WorkflowExecutionError(WorkflowError):
    """Step execution failed unrecoverably."""


# ── Multimodal ─────────────────────────────────────────────────────────────────

class TranscriptionError(ZeError):
    """Audio file could not be transcribed by the Whisper model."""


class ImageDownloadError(ZeError):
    """Failed to download image bytes from Telegram's file server."""


# ── Browser ────────────────────────────────────────────────────────────────────

class BrowserError(ZeError):
    """ze-browser sidecar request failed (connection error or 5xx)."""


# ── Channels ───────────────────────────────────────────────────────────────────

class ChannelError(ZeError):
    """Base class for communication channel errors."""


class ChannelNotFoundError(ChannelError):
    """No channel registered for the requested ChannelType."""


class ChannelSendError(ChannelError):
    """Channel transport failed during send."""


# ── Goals ──────────────────────────────────────────────────────────────────────

class GoalError(ZeError):
    """Base class for goal engine errors."""


class GoalPlanError(GoalError):
    """Planner returned invalid output."""


class GoalExecutionError(GoalError):
    """Milestone execution failed."""
