#!/usr/bin/env python3
"""Manage the ZE API token inside the repo-level .env file."""

from __future__ import annotations

import argparse
import secrets
from pathlib import Path

ROOT_ENV = Path(".env")
EXAMPLE_ENV = Path(".env.example")
PLACEHOLDERS = {"", "change-me"}


def ensure_env_file() -> None:
    if ROOT_ENV.exists():
        return
    if not EXAMPLE_ENV.exists():
        raise SystemExit(f"{EXAMPLE_ENV} is missing; create it first.")
    ROOT_ENV.write_text(EXAMPLE_ENV.read_text())
    print(f"Created {ROOT_ENV} from {EXAMPLE_ENV}")


def read_value(key: str) -> str:
    for line in ROOT_ENV.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return ""


def update_values(values: dict[str, str]) -> bool:
    lines = ROOT_ENV.read_text().splitlines()
    updated = False
    seen: set[str] = set()

    for index, line in enumerate(lines):
        for key, value in values.items():
            if line.startswith(f"{key}="):
                seen.add(key)
                if line != f"{key}={value}":
                    lines[index] = f"{key}={value}"
                    updated = True
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
            updated = True

    if updated:
        ROOT_ENV.write_text("\n".join(lines) + "\n")
    return updated


def canonical_token(existing: str, frontend: str, override: str | None) -> str:
    if override:
        return override
    if existing and existing not in PLACEHOLDERS:
        return existing
    if frontend and frontend not in PLACEHOLDERS:
        return frontend
    return secrets.token_urlsafe(32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/sync the ZE API key inside .env")
    parser.add_argument("--token", help="Explicit token to use instead of generating a random one")
    args = parser.parse_args()

    ensure_env_file()
    backend_token = read_value("ZE_API_KEY")
    frontend_token = read_value("NEXT_PUBLIC_ZE_API_KEY")
    token = canonical_token(backend_token, frontend_token, args.token)

    values = {
        "ZE_API_KEY": token,
        "NEXT_PUBLIC_ZE_API_KEY": token,
    }
    changed = update_values(values)

    print(f"ZE API token: {token}")
    if not changed:
        print("No changes were necessary.")
    else:
        print(f"Updated {ROOT_ENV}")


if __name__ == "__main__":
    main()
