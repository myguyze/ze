from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from ze_seed.context import SeedContext


@dataclass
class SeedDomain:
    """Describes one seedable data slice with namespace-isolated clear/apply."""

    name: str
    seed_order: int
    clear: Callable[["SeedContext"], Awaitable[None]]
    apply: Callable[["SeedContext"], Awaitable[int]]
