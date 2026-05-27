from __future__ import annotations

from typing import Protocol, runtime_checkable

from ze_core.telemetry.types import CostRecord


@runtime_checkable
class CostStore(Protocol):
    async def write(self, rec: CostRecord) -> None: ...
