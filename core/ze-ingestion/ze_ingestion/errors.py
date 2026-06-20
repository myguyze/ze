from __future__ import annotations

from ze_agents.errors import ZeError


class FetchError(ZeError):
    """Raised when a fetcher cannot retrieve content."""


class ProcessError(ZeError):
    """Raised when a processor fails to convert raw content."""


class UnsupportedContentError(ZeError):
    """Raised when no processor supports the classified content type."""
