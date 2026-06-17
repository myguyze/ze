from __future__ import annotations

from typing import TYPE_CHECKING

from ze_sdk import ZePlugin
from ze_email.channel.gmail import GmailChannel

if TYPE_CHECKING:
    from ze_google.auth import GoogleCredentials


class EmailPlugin(ZePlugin):
    """Registers the Gmail email agent and exposes the Gmail channel."""

    def __init__(self, google_credentials: GoogleCredentials | None = None) -> None:
        self._google_credentials = google_credentials

    @property
    def gmail_channel(self) -> GmailChannel | None:
        if self._google_credentials is None:
            return None
        return GmailChannel(credentials=self._google_credentials)

    def channels(self) -> list:
        ch = self.gmail_channel
        return [ch] if ch is not None else []

    def memory_policies(self) -> dict:
        from ze_memory.policies import EmailPolicy

        return {"email": EmailPolicy()}

    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_google.auth import GoogleCredentials
        return [GoogleCredentials]

    def agent_module_paths(self) -> list[str]:
        if self._google_credentials is None:
            return []
        return [
            "ze_email.agents.email.tools",
            "ze_email.agents.email.agent",
        ]
