from dataclasses import dataclass


@dataclass
class CostRecord:
    agent: str
    flow_type: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    session_id: str | None
    cost_usd: float | None
    generation_id: str | None  # OpenRouter generation ID — use GET /api/v1/generation?id= for exact cost
    audio_seconds: float | None = None  # set for Whisper calls; token fields are 0 for audio
