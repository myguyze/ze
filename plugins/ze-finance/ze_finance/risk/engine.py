from __future__ import annotations

from typing import Protocol

from ze_finance.risk.types import FactorExposure
from ze_finance.types import Position


class RiskEngine(Protocol):
    """ze-risk will provide a concrete implementation; ze-finance never instantiates one."""

    async def compute_exposures(self, positions: list[Position]) -> list[FactorExposure]: ...
    async def check_drift(self, exposures: list[FactorExposure]) -> list[str]: ...
