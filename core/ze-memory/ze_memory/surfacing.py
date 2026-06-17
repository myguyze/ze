"""Hypothesis surfacing gate — Phase 56.

Defines the two-tier bar that decides whether a formed hypothesis (Phase 57)
is allowed to reach the user:

  inline  (Phase 58) — low bar; user initiated the turn, no interruption
  push    (Phase 59, deferred) — high bar; unsolicited interrupt

The feedback path (useful / not_relevant / mute_topic) nudges thresholds
within [tau_min, tau_max] clamps.  Global thresholds in v1; per-topic
overrides are a Phase 60+ concern.
"""
from __future__ import annotations

from dataclasses import dataclass

from ze_agents.logging import get_logger

log = get_logger(__name__)


@dataclass
class SurfacingConfig:
    tau_push: float = 0.6
    tau_inline: float = 0.45
    tau_relevance: float = 0.5
    min_evidence: int = 2
    novelty_similarity_max: float = 0.85
    max_pushes_per_day: int = 3
    feedback_step: float = 0.05
    tau_min: float = 0.4
    tau_max: float = 0.85

    @classmethod
    def from_config(cls, cfg: dict) -> "SurfacingConfig":
        surfacing = cfg.get("surfacing", {})
        budget = cfg.get("budget", {})
        feedback = cfg.get("feedback", {})
        return cls(
            tau_push=float(surfacing.get("tau_push", 0.6)),
            tau_inline=float(surfacing.get("tau_inline", 0.45)),
            tau_relevance=float(surfacing.get("tau_relevance", 0.5)),
            min_evidence=int(surfacing.get("min_evidence", 2)),
            novelty_similarity_max=float(surfacing.get("novelty_similarity_max", 0.85)),
            max_pushes_per_day=int(budget.get("max_pushes_per_day", 3)),
            feedback_step=float(feedback.get("step", 0.05)),
            tau_min=float(feedback.get("tau_min", 0.4)),
            tau_max=float(feedback.get("tau_max", 0.85)),
        )


class SurfacingGate:
    """Checks whether a hypothesis may be surfaced to the user.

    Used by Phase 58 (inline) and Phase 59 (push, deferred post-v1).
    Feedback reactions tune thresholds in place.
    """

    def __init__(self, config: SurfacingConfig) -> None:
        self._cfg = config

    @property
    def config(self) -> SurfacingConfig:
        return self._cfg

    def check_inline(
        self,
        *,
        confidence: float,
        evidence_count: int,
    ) -> tuple[bool, list[str]]:
        """Return (passed, blocking_reasons) for inline surfacing.

        Inline bar is minimal — user already initiated the turn (implicit relevance)
        and there is no interruption.
        """
        reasons: list[str] = []
        if evidence_count < self._cfg.min_evidence:
            reasons.append(
                f"insufficient evidence: {evidence_count} < {self._cfg.min_evidence}"
            )
        if confidence < self._cfg.tau_inline:
            reasons.append(
                f"confidence too low: {confidence:.2f} < {self._cfg.tau_inline}"
            )
        return len(reasons) == 0, reasons

    def check_push(
        self,
        *,
        confidence: float,
        evidence_count: int,
        relevance: float,
        is_novel: bool,
        within_budget: bool,
    ) -> tuple[bool, list[str]]:
        """Return (passed, blocking_reasons) for proactive push (Phase 59).

        All conditions must hold — a failed push is stored for digest/recall, not discarded.
        """
        reasons: list[str] = []
        if evidence_count < self._cfg.min_evidence:
            reasons.append(
                f"insufficient evidence: {evidence_count} < {self._cfg.min_evidence}"
            )
        if confidence < self._cfg.tau_push:
            reasons.append(
                f"confidence too low: {confidence:.2f} < {self._cfg.tau_push}"
            )
        if relevance < self._cfg.tau_relevance:
            reasons.append(
                f"relevance too low: {relevance:.2f} < {self._cfg.tau_relevance}"
            )
        if not is_novel:
            reasons.append(
                "not novel: embedding similarity too high to a recent push"
            )
        if not within_budget:
            reasons.append(
                f"push budget exceeded: max {self._cfg.max_pushes_per_day}/day"
            )
        return len(reasons) == 0, reasons

    def apply_feedback(self, reaction: str) -> None:
        """Nudge global thresholds based on user reaction.

        useful       → lower thresholds (more like this)
        not_relevant → raise thresholds (fewer like this)
        mute_topic   → caller writes a news_exclusion-style preference; gate unchanged
        """
        step = self._cfg.feedback_step
        lo = self._cfg.tau_min
        hi = self._cfg.tau_max

        if reaction == "useful":
            self._cfg.tau_push = max(lo, self._cfg.tau_push - step)
            self._cfg.tau_inline = max(lo, self._cfg.tau_inline - step)
            self._cfg.tau_relevance = max(lo, self._cfg.tau_relevance - step)
            log.info(
                "surfacing_threshold_nudged",
                direction="down",
                tau_push=self._cfg.tau_push,
                tau_inline=self._cfg.tau_inline,
            )
        elif reaction == "not_relevant":
            self._cfg.tau_push = min(hi, self._cfg.tau_push + step)
            self._cfg.tau_inline = min(hi, self._cfg.tau_inline + step)
            self._cfg.tau_relevance = min(hi, self._cfg.tau_relevance + step)
            log.info(
                "surfacing_threshold_nudged",
                direction="up",
                tau_push=self._cfg.tau_push,
                tau_inline=self._cfg.tau_inline,
            )
