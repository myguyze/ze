from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ZeIntegration(Protocol):
    """Structural protocol for integration credentials classes.

    Integration packages (under integrations/) never import this — they satisfy
    it structurally by implementing from_settings. Used by the bootstrapper for
    validation only.
    """

    @classmethod
    def from_settings(cls, settings: Any) -> "ZeIntegration | None":
        """Build from app settings. Return None if not configured."""
        ...
