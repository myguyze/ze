from __future__ import annotations

from ze_agents.errors import ZeError


class FinanceError(ZeError):
    """Base class for ze-finance errors."""


class ZeIntegrationError(FinanceError):
    """A data source integration call failed (e.g. Trading212 4xx/5xx)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FinanceParseError(FinanceError):
    """CSV or data parsing failed."""
