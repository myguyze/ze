from dataclasses import dataclass, field


@dataclass
class SubTask:
    agent: str
    intent: str    # "read" | "create" | "update" | "delete" | "execute" | "reason"
    prompt: str    # isolated prompt for this subtask only


@dataclass
class RoutingEnvelope:
    primary_agent: str
    confidence: float            # top cosine score (0–1)
    score_gap: float             # scores[0] - scores[1]; 0.0 for single-agent or haiku
    routing_method: str          # "embedding" | "haiku"
    is_compound: bool
    subtasks: list[SubTask]      # always at least one entry
    requires_synthesis: bool     # True when len(subtasks) > 1
    raw_scores: dict[str, float] = field(default_factory=dict)
