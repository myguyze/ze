from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class FactorTaxonomy(str, Enum):
    # Primary — drive drift alerts on their own
    AI_SENTIMENT = "ai_sentiment"
    RISK_APPETITE = "risk_appetite"
    CRYPTO_MOMENTUM = "crypto_momentum"
    SEMICONDUCTOR_CYCLE = "semiconductor_cycle"
    EM_STRESS = "em_stress"
    # Amplifiers — tighten thresholds when elevated
    LIQUIDITY_STRESS = "liquidity_stress"
    DOLLAR_STRENGTH = "dollar_strength"
    VOLATILITY_REGIME = "volatility_regime"
    GEOPOLITICAL_TENSION = "geopolitical_tension"
    # Structural — slower-moving, monitored for regime shifts
    RATE_REGIME = "rate_regime"
    TECH_REGULATION = "tech_regulation"
    CHINA_RISK = "china_risk"
    MIDDLE_EAST_RISK = "middle_east_risk"


@dataclass
class FactorExposure:
    """Placeholder. Phase 67 never populates this — it is the ze-risk contract."""

    factor: FactorTaxonomy
    exposure: Decimal  # portfolio-level exposure weight (-1 to +1)
    notional: Decimal  # USD notional driving this exposure


@dataclass
class FactorReading:
    """A single time-series observation of a factor's value."""

    factor: FactorTaxonomy
    value: float  # normalised z-score or raw reading depending on factor
    source: str
    observed_at: datetime
