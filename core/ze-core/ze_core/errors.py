class ZeCoreError(Exception):
    """Base exception for all Ze Core errors."""


# ── Routing ───────────────────────────────────────────────────────────────────

class RoutingError(ZeCoreError):
    """Routing failed after all attempts."""


class InvalidPromptError(RoutingError):
    """Prompt is empty or invalid."""


# ── Agents ────────────────────────────────────────────────────────────────────

class AgentError(ZeCoreError):
    """An agent failed during execution."""


class AgentTimeoutError(AgentError):
    """Agent exceeded its configured timeout."""


class UnknownAgentError(AgentError):
    """No agent registered for the requested name."""


class AgentConfigError(AgentError):
    """Agent or tool misconfiguration detected at startup."""


# ── Interface ─────────────────────────────────────────────────────────────────

class InterfaceError(ZeCoreError):
    """Base class for interface errors."""


class InterfaceConfigError(InterfaceError):
    """AppInterface implementation is misconfigured."""


# ── Capability ────────────────────────────────────────────────────────────────

class CapabilityError(ZeCoreError):
    """Capability gate error."""


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryError(ZeCoreError):
    """Memory store operation failed."""


# ── Tools ─────────────────────────────────────────────────────────────────────

class UnknownToolError(AgentError):
    """No tool registered for the requested name."""


class ToolBlockedError(AgentError):
    """Tool call rejected because the capability gate is BLOCKED."""


# ── Workflow ──────────────────────────────────────────────────────────────────

class WorkflowError(ZeCoreError):
    """Base class for workflow errors."""


class WorkflowPlanError(WorkflowError):
    """Planner failed to produce a valid workflow plan."""


class WorkflowExecutionError(WorkflowError):
    """Step execution failed unrecoverably."""


# ── Goals ─────────────────────────────────────────────────────────────────────

class GoalError(ZeCoreError):
    """Base class for goal errors."""


class GoalPlanError(GoalError):
    """Goal planner returned an invalid or unparseable plan."""


class GoalExecutionError(GoalError):
    """A milestone failed during goal execution."""


# ── Persona ───────────────────────────────────────────────────────────────────

class PersonaError(ZeCoreError):
    """Base class for persona errors."""


class UnknownProfileError(PersonaError):
    """Named persona profile not found."""


class UnknownDialError(PersonaError):
    """Named persona dial not found."""


# ── OpenRouter ────────────────────────────────────────────────────────────────

class OpenRouterError(ZeCoreError):
    """OpenRouter API call failed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(OpenRouterError):
    """OpenRouter returned HTTP 429."""


# ── Harness ───────────────────────────────────────────────────────────────────

class AgentAbortedError(AgentError):
    """Raised inside agentic_loop when an AbortToken fires or on_loop_start aborts."""

    def __init__(self, reason: str | None = None) -> None:
        super().__init__(reason or "aborted")
        self.reason = reason


class HookAbort(AgentError):
    """Raised from HarnessHook.on_tool_start to skip a single tool call.

    The loop records the skipped call and continues to the next LLM turn.
    """

    def __init__(self, tool_name: str, reason: str = "") -> None:
        super().__init__(f"hook aborted {tool_name!r}: {reason}")
        self.tool_name = tool_name
        self.reason = reason


# ── Channels ──────────────────────────────────────────────────────────────────

class ChannelError(ZeCoreError):
    """Base class for channel errors."""


class ChannelNotFoundError(ChannelError):
    """No channel registered for the requested channel type."""


class ChannelSendError(ChannelError):
    """Channel transport failed during send."""
