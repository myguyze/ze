from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ZE_API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "ze-api"


class GoogleSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ZE_API_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""


@lru_cache
def get_google_settings() -> GoogleSettings:
    return GoogleSettings()
