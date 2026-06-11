"""Ze application exceptions."""

from ze_core.errors import ChannelError, ChannelSendError, ZeCoreError as ZeError

# ── Capability ────────────────────────────────────────────────────────────────

class CapabilityError(ZeError):
    """Capability gate error."""


class CapabilityConfigError(CapabilityError):
    """capabilities.yaml could not be loaded or is invalid."""


# ── Memory ────────────────────────────────────────────────────────────────────

class MemoryError(ZeError):
    """Memory store operation failed."""


# ── Multimodal ─────────────────────────────────────────────────────────────────

class TranscriptionError(ZeError):
    """Audio file could not be transcribed by the Whisper model."""


class ImageDownloadError(ZeError):
    """Failed to download image bytes from Telegram's file server."""


