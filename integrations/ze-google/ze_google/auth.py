from __future__ import annotations

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]

_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleCredentials:
    """Wraps a Google OAuth2 refresh token and provides service client factories.

    The underlying Credentials object refreshes the access token automatically
    when it expires — no manual refresh logic required.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        self._creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

    def calendar(self):
        """Return a Google Calendar API v3 service client."""
        return build("calendar", "v3", credentials=self._creds)

    def gmail(self):
        """Return a Gmail API v1 service client."""
        return build("gmail", "v1", credentials=self._creds)

    @classmethod
    def from_settings(cls, settings) -> GoogleCredentials | None:
        """Return None if any required credential env var is unset."""
        if not all([
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_refresh_token,
        ]):
            return None
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            refresh_token=settings.google_refresh_token,
        )
