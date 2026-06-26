from __future__ import annotations

from typing import TYPE_CHECKING

from ze_sdk import ZePlugin

if TYPE_CHECKING:
    from ze_google.auth import GoogleCredentials


class MessengerPlugin(ZePlugin):
    """Registers the messenger agent and exposes communication channels."""

    def __init__(self, google_credentials: GoogleCredentials | None = None) -> None:
        self._google_credentials = google_credentials

    def channels(self) -> list:
        if self._google_credentials is None:
            return []
        from ze_google.gmail_channel import GmailChannel
        return [GmailChannel(credentials=self._google_credentials)]

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
            "ze_messenger.agents.messenger.tools",
            "ze_messenger.agents.messenger.agent",
        ]
