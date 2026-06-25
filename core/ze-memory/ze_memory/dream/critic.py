"""Two-call adversarial LLM critic for dream artifacts."""
from __future__ import annotations

from typing import Any

from ze_logging import get_logger

log = get_logger(__name__)

_DEFAULT_CRITIC_MODEL = "anthropic/claude-sonnet-4-6"

_CALL_A_SYSTEM = (
    "You are an adversarial fact-checker. Your job is to find every way a claim could be "
    "wrong, overstated, contradicted, or unsupported by its sources. Be rigorous. "
    "If the claim contains a negation, explicitly verify the negation is supported.\n"
    "Reply with exactly: PASS\n"
    "or: FAIL: <one sentence reason>"
)

_CALL_B_SYSTEM = (
    "You are a constructive citation verifier. Your job is to confirm that every claim "
    "is traceable to a specific source passage. List any claims that lack a clear source.\n"
    "Reply with exactly: PASS\n"
    "or: FAIL: <citation gaps>"
)


class DreamCritic:
    def __init__(self, client: Any, model: str = _DEFAULT_CRITIC_MODEL) -> None:
        self._client = client
        self._model = model

    async def critique_artifact(
        self,
        content: str,
        source_texts: list[str],
    ) -> tuple[str, str | None, str, str | None]:
        """
        Run Call A (challenge) then Call B (verify).
        Returns (a_verdict, a_reason, b_verdict, b_reason).
        b_* are None if A fails — skip B on early failure.
        """
        source_block = "\n---\n".join(source_texts[:5]) if source_texts else "(no sources)"

        a_verdict, a_reason = await self._call(
            system=_CALL_A_SYSTEM,
            content=content,
            source_block=source_block,
            temperature=0.1,
            label="critic_a",
        )

        if a_verdict != "PASS":
            return a_verdict, a_reason, "FAIL", "skipped — Call A failed"

        b_verdict, b_reason = await self._call(
            system=_CALL_B_SYSTEM,
            content=content,
            source_block=source_block,
            temperature=0.3,
            label="critic_b",
        )

        return a_verdict, a_reason, b_verdict, b_reason

    async def _call(
        self,
        system: str,
        content: str,
        source_block: str,
        temperature: float,
        label: str,
    ) -> tuple[str, str | None]:
        prompt = (
            f"SOURCE MATERIAL:\n{source_block}\n\n"
            f"CLAIM TO EVALUATE:\n{content}"
        )
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": prompt}],
                model=self._model,
                system=system,
                temperature=temperature,
                max_tokens=200,
            )
        except Exception as exc:
            log.warning(f"{label}_error", error=str(exc))
            return "FAIL", f"critic error: {exc}"

        raw = raw.strip()
        if raw.upper().startswith("PASS"):
            return "PASS", None
        if raw.upper().startswith("FAIL"):
            reason = raw[4:].lstrip(": ").strip() or "critic rejected"
            return "FAIL", reason
        # Ambiguous response — treat as pass to avoid over-rejection
        log.warning(f"{label}_ambiguous_response", response=raw[:100])
        return "PASS", None
