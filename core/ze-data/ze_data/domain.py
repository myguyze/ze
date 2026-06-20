from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class DataDomain:
    """Describes one data domain that a plugin owns and can export/import/delete."""

    name: str
    export: Callable[[Any], Awaitable[list[dict]]]
    delete: Callable[[Any], Awaitable[None]]
    # Lower delete_order = deleted first (children before parents).
    # Import order is the reverse: higher delete_order imported first (parents first).
    delete_order: int = 50
    # None means this domain is not importable (e.g. opaque LangGraph checkpoint blobs).
    # Receives an asyncpg Connection (not pool) so importers run inside one transaction.
    importer: Callable[[Any, list[dict]], Awaitable[int]] | None = None
