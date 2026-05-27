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


# ── Channels ──────────────────────────────────────────────────────────────────

class ChannelError(ZeCoreError):
    """Base class for channel errors."""


class ChannelNotFoundError(ChannelError):
    """No channel registered for the requested channel type."""
