from unittest.mock import MagicMock

from ze_google.auth import GoogleCredentials


def test_from_settings_returns_none_when_unconfigured() -> None:
    settings = MagicMock(
        google_client_id=None,
        google_client_secret=None,
        google_refresh_token=None,
    )
    assert GoogleCredentials.from_settings(settings) is None


def test_from_settings_returns_credentials_when_configured() -> None:
    settings = MagicMock(
        google_client_id="id",
        google_client_secret="secret",
        google_refresh_token="token",
    )
    creds = GoogleCredentials.from_settings(settings)
    assert creds is not None
    assert isinstance(creds, GoogleCredentials)
