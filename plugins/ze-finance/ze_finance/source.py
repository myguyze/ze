from __future__ import annotations

from datetime import datetime
from typing import Protocol

from ze_finance.types import Account, Position, Transaction


class DataSource(Protocol):
    @property
    def source_id(self) -> str:
        """Stable identifier for this source (e.g. 'trading212', 'csv:revolut')."""
        ...

    async def fetch_account(self) -> Account: ...
    async def fetch_positions(self) -> list[Position]: ...
    async def fetch_transactions(self, since: datetime) -> list[Transaction]: ...
