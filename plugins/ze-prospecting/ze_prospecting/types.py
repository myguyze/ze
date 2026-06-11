from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProspectingSettings:
    max_iterations: int = 15
    max_loop_tokens: int = 24_000
    stale_timeout_minutes: int = 10
    browser_delay_ms: int = 2000
    browser_max_text_chars: int = 8000

    @classmethod
    def from_env(cls) -> ProspectingSettings:
        return cls(
            max_iterations=int(os.environ.get("PROSPECTING_MAX_ITERATIONS", "15")),
            max_loop_tokens=int(os.environ.get("PROSPECTING_MAX_LOOP_TOKENS", "24000")),
            stale_timeout_minutes=int(os.environ.get("PROSPECTING_STALE_TIMEOUT_MINUTES", "10")),
            browser_delay_ms=int(os.environ.get("BROWSER_DELAY_MS", "2000")),
            browser_max_text_chars=int(os.environ.get("BROWSER_MAX_TEXT_CHARS", "8000")),
        )
