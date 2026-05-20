import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ComplexityResult:
    complexity: str  # "simple" | "complex"
    score: int       # negative = simple evidence; positive = complex evidence


class ComplexityEstimator:
    """Pure-function classifier. No I/O. No LLM calls."""

    _COMPLEX_PATTERNS = re.compile(
        r"\b("
        r"explain why|analyz[ei]|analys[ei]|compar[ei]"
        r"|why does|why do|how does|how do"
        r"|help me (understand|think|reason|decide)"
        r"|synthesiz[ei]|synthes[ei]s"
        r"|should i|should we"
        r"|evaluat[ei]|assess"
        r"|implication|trade.?off|pros and cons"
        r"|deep dive|walk me through|think through|brainstorm"
        r"|critically|in depth|in detail"
        r")\b",
        re.IGNORECASE,
    )

    _SIMPLE_PATTERNS = re.compile(
        r"\b("
        r"what is|what's the|what are"
        r"|who is|who's the"
        r"|when did|when was|when is"
        r"|where is|where was"
        r"|define|definition of"
        r"|how many|how much"
        r"|list the|give me a list|list of"
        r")\b",
        re.IGNORECASE,
    )

    def classify(self, prompt: str, intent: str, confidence: float) -> str:
        score = 0

        # Word count
        word_count = len(prompt.split())
        if word_count > 30:
            score += 2
        elif word_count < 12:
            score -= 1

        # Intent
        if intent == "reason":
            score += 2

        # Keyword matches (each pattern list capped at ±4)
        complex_hits = len(self._COMPLEX_PATTERNS.findall(prompt))
        simple_hits = len(self._SIMPLE_PATTERNS.findall(prompt))
        score += min(complex_hits * 2, 4)
        score -= min(simple_hits * 2, 4)

        # High routing confidence is a weak simple signal
        if confidence > 0.80:
            score -= 1

        complexity = "simple" if score < -1 else "complex"
        return complexity
