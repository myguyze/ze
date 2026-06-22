from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ZE_API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "ze-api"


class Trading212Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_ZE_API_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    trading212_api_key: str = ""
    trading212_demo: bool = False


@lru_cache
def get_trading212_settings() -> Trading212Settings:
    return Trading212Settings()
