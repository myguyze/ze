#!/usr/bin/env python3
"""Generate or update ZE_API_KEY in the repo-level .env file.

Usage:
    uv run python scripts/generate_ze_api_key.py
    uv run python scripts/generate_ze_api_key.py --token my-secret
"""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ENV = _ROOT / ".env"
_EXAMPLE = _ROOT / ".env.example"
_KEY = "ZE_API_KEY"
_PLACEHOLDER = "change-me"


def ensure_env_file() -> None:
    if _ENV.exists():
        return
    if not _EXAMPLE.exists():
        raise SystemExit(f"{_EXAMPLE} is missing; create it first.")
    _ENV.write_text(_EXAMPLE.read_text())
    print(f"Created {_ENV.relative_to(_ROOT)} from {_EXAMPLE.name}")


def read_key() -> str:
    for line in _ENV.read_text().splitlines():
        if line.startswith(f"{_KEY}="):
            return line.split("=", 1)[1]
    return ""


def write_key(value: str) -> bool:
    lines = _ENV.read_text().splitlines()
    target = f"{_KEY}={value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{_KEY}="):
            if line == target:
                return False
            lines[index] = target
            _ENV.write_text("\n".join(lines) + "\n")
            return True
    lines.append(target)
    _ENV.write_text("\n".join(lines) + "\n")
    return True


def resolve_token(existing: str, override: str | None) -> str:
    if override:
        return override
    if existing and existing != _PLACEHOLDER:
        return existing
    return secrets.token_urlsafe(32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or update ZE_API_KEY in .env")
    parser.add_argument("--token", help="Use this token instead of generating one")
    args = parser.parse_args()

    ensure_env_file()
    token = resolve_token(read_key(), args.token)
    changed = write_key(token)

    print(f"ZE_API_KEY={token}")
    if changed:
        print(f"Updated {_ENV.relative_to(_ROOT)}")
    else:
        print("No changes were necessary.")


if __name__ == "__main__":
    main()
