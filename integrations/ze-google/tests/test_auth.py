from unittest.mock import MagicMock

import pytest

from ze_google.auth import GoogleCredentials
from ze_google.settings import get_google_settings


@pytest.fixture(autouse=True)
def clear_google_settings_cache():
    get_google_settings.cache_clear()
    yield
    get_google_settings.cache_clear()


def test_from_settings_returns_none_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "")
    get_google_settings.cache_clear()
    assert GoogleCredentials.from_settings(None) is None


def test_from_settings_returns_credentials_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REFRESH_TOKEN", "token")
    get_google_settings.cache_clear()
    creds = GoogleCredentials.from_settings(MagicMock())
    assert creds is not None
    assert isinstance(creds, GoogleCredentials)
