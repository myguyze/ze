"""
Programmatic migration runner for Ze Core.

Usage from Python:
    from ze_core.migrate import upgrade
    upgrade("postgresql+psycopg2://user:pass@localhost/db")

Usage from the shell:
    python -m ze_core.migrate                       # upgrade head
    python -m ze_core.migrate upgrade head
    python -m ze_core.migrate downgrade -1
    python -m ze_core.migrate current
    python -m ze_core.migrate history

DATABASE_URL_SYNC must be set in the environment if database_url is not
passed explicitly.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _config(database_url: str) -> Any:
    try:
        from alembic.config import Config
    except ImportError as exc:
        raise ImportError(
            "alembic is required to run migrations."
            " Install it with: pip install 'ze-core[migrations]'"
        ) from exc

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def upgrade(database_url: str | None = None, revision: str = "head") -> None:
    """Apply all pending migrations up to `revision` (default: head)."""
    from alembic import command
    command.upgrade(_config(_resolve_url(database_url)), revision)


def downgrade(database_url: str | None = None, revision: str = "-1") -> None:
    """Roll back to `revision`."""
    from alembic import command
    command.downgrade(_config(_resolve_url(database_url)), revision)


def current(database_url: str | None = None) -> None:
    """Print the current revision."""
    from alembic import command
    command.current(_config(_resolve_url(database_url)))


def history(database_url: str | None = None) -> None:
    """Print migration history."""
    from alembic import command
    command.history(_config(_resolve_url(database_url)))


def _resolve_url(database_url: str | None) -> str:
    if database_url:
        return database_url
    url = os.environ.get("DATABASE_URL_SYNC", "")
    if not url:
        raise RuntimeError(
            "Pass database_url explicitly or set DATABASE_URL_SYNC in the environment."
        )
    return url


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    cmd = args[0] if args else "upgrade"
    rev = args[1] if len(args) > 1 else None

    url = _resolve_url(None)

    if cmd == "upgrade":
        upgrade(url, rev or "head")
    elif cmd == "downgrade":
        downgrade(url, rev or "-1")
    elif cmd == "current":
        current(url)
    elif cmd == "history":
        history(url)
    else:
        print(
            f"Unknown command: {cmd!r}\n"
            "Usage: python -m ze_core.migrate [upgrade|downgrade|current|history] [revision]",
            file=sys.stderr,
        )
        sys.exit(1)
