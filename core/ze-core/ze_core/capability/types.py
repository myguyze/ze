from enum import Enum


class Mode(str, Enum):
    AUTONOMOUS = "autonomous"
    CONFIRM    = "confirm"
    DRAFT_ONLY = "draft_only"
    DISABLED   = "disabled"


class GateDecision(str, Enum):
    EXECUTE            = "execute"
    DRAFT              = "draft"
    AWAIT_CONFIRMATION = "confirm"
    BLOCKED            = "blocked"
