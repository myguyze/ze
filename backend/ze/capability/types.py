from dataclasses import dataclass
from enum import Enum


class GateDecision(Enum):
    EXECUTE = "execute"
    DRAFT = "draft"
    AWAIT_CONFIRMATION = "confirm"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CapabilityConfig:
    mode: str  # "autonomous" | "confirm" | "draft_only" | "disabled"
