from __future__ import annotations

from ze_agents.errors import ZeError


class LoopNotFoundError(ZeError):
    """Unknown loop id on a read/transition request."""


class InvalidLoopTransitionError(ZeError):
    """Attempted transition not permitted from the loop's current state."""
