from __future__ import annotations

import random
from pathlib import Path

import yaml

from ze_core.logging import get_logger

log = get_logger(__name__)


class ProgressTranslations:
    def __init__(self, data: dict, fallback: dict) -> None:
        self._data = data
        self._fallback = fallback

    @classmethod
    def load(cls, locale: str, config_dir: Path) -> "ProgressTranslations":
        en = cls._load_file(config_dir / "locales" / "en.yaml")
        if locale == "en":
            return cls(data=en, fallback=en)
        target = cls._load_file(config_dir / "locales" / f"{locale}.yaml")
        return cls(data=target, fallback=en)

    def resolve(self, key: str, **kwargs: str) -> str | None:
        """
        Resolve a dotted key to a localized string, falling back to English.
        Returns None if the key is unknown in both — callers skip the emit.
        """
        text = self._lookup(self._data, key) or self._lookup(self._fallback, key)
        if text is None:
            log.warning("progress_key_missing", key=key)
            return None
        return text.format(**kwargs) if kwargs else text

    @staticmethod
    def _load_file(path: Path) -> dict:
        try:
            return yaml.safe_load(path.read_text()) or {}
        except Exception as exc:
            log.warning("progress_locale_load_failed", path=str(path), error=str(exc))
            return {}

    @staticmethod
    def _lookup(d: dict, key: str) -> str | None:
        val: object = d
        for part in key.split("."):
            if not isinstance(val, dict) or part not in val:
                return None
            val = val[part]
        if isinstance(val, list):
            return random.choice(val) if val else None
        if isinstance(val, str):
            return val
        return None
