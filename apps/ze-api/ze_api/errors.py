"""Ze application exceptions."""

from ze_agents.errors import (
    OnboardingError as OnboardingError,
    ZeCoreError as ZeError,
)  # noqa: F401

# ── Capability ────────────────────────────────────────────────────────────────


class CapabilityError(ZeError):
    """Capability gate error."""


class CapabilityConfigError(CapabilityError):
    """capabilities.yaml could not be loaded or is invalid."""


# ── Migrations ────────────────────────────────────────────────────────────────


class MigrationReadinessError(ZeError):
    """Database migrations are not at the expected Alembic heads."""


# ── Memory ────────────────────────────────────────────────────────────────────


class MemoryError(ZeError):
    """Memory store operation failed."""


# ── Multimodal ─────────────────────────────────────────────────────────────────


class TranscriptionError(ZeError):
    """Audio file could not be transcribed by the Whisper model."""


class ImageDownloadError(ZeError):
    """Failed to download image bytes from Telegram's file server."""
