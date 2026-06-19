"""
Programmatic migration runner for Ze.

Discovers migration paths from ze-core, ze-api, and all registered ZePlugin subclasses.
Plugin modules listed in _PLUGIN_MODULES are imported at startup so their
__init_subclass__ hooks fire and populate the ze_plugin registry.

Usage from the shell (via Makefile):
    python -m ze_api.migrate                         # upgrade heads
    python -m ze_api.migrate upgrade [revision]
    python -m ze_api.migrate downgrade [revision]    # default: -1
    python -m ze_api.migrate current
    python -m ze_api.migrate history
    python -m ze_api.migrate heads
    python -m ze_api.migrate stamp <rev> [<rev>...]
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, pool
import ze_core
import ze_memory
import ze_onboarding
import ze_correlation
import ze_proactive

from ze_api.errors import MigrationReadinessError

# Ordered list of plugin modules to import before collecting migration paths.
# Importing triggers __init_subclass__ registration in ze_plugin.registry._registry.
_PLUGIN_MODULES: list[str] = [
    "ze_personal.plugin",
    "ze_calendar.plugin",
    "ze_email.plugin",
    "ze_news.plugin",
    "ze_finance.plugin",
    "ze_prospecting.plugin",
]

# Fixed script_location: the ze migrations directory contains env.py and script.py.mako.
_SCRIPT_LOCATION = Path(__file__).parent / "migrations"

# Core package version paths (not ZePlugin subclasses — registered explicitly).
_ZE_CORE_VERSIONS = Path(ze_core.__file__).parent / "migrations" / "versions"
_ZE_MEMORY_VERSIONS = Path(ze_memory.__file__).parent / "migrations" / "versions"
_ZE_ONBOARDING_VERSIONS = Path(ze_onboarding.__file__).parent / "migrations" / "versions"
_ZE_CORRELATION_VERSIONS = Path(ze_correlation.__file__).parent / "migrations" / "versions"
_ZE_PROACTIVE_VERSIONS = Path(ze_proactive.__file__).parent / "migrations" / "versions"
_ZE_VERSIONS = _SCRIPT_LOCATION / "versions"


def _import_plugins() -> None:
    for module_path in _PLUGIN_MODULES:
        try:
            importlib.import_module(module_path)
        except ImportError:
            pass


def _collect_version_locations() -> list[Path]:
    _import_plugins()

    from ze_plugin.registry import get_plugin_registry

    paths: list[Path] = [
        _ZE_CORE_VERSIONS,
        _ZE_MEMORY_VERSIONS,
        _ZE_ONBOARDING_VERSIONS,
        _ZE_CORRELATION_VERSIONS,
        _ZE_PROACTIVE_VERSIONS,
        _ZE_VERSIONS,
    ]
    for plugin_cls in get_plugin_registry():
        plugin_path = plugin_cls.migrations_path()
        if plugin_path is not None:
            versions_dir = plugin_path / "versions" if (plugin_path / "versions").exists() else plugin_path
            if versions_dir not in paths and versions_dir.exists():
                paths.append(versions_dir)

    return paths


def _build_config(database_url: str) -> Any:
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.set_main_option("version_path_separator", "os")
    cfg.set_main_option(
        "version_locations",
        os.pathsep.join(str(p) for p in _collect_version_locations()),
    )
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _resolve_url(database_url: str | None) -> str:
    if database_url:
        return database_url
    url = os.environ.get("DATABASE_URL_SYNC", "")
    if not url:
        raise RuntimeError(
            "Pass database_url explicitly or set DATABASE_URL_SYNC in the environment."
        )
    return url


def upgrade(database_url: str | None = None, revision: str = "heads") -> None:
    from alembic import command
    command.upgrade(_build_config(_resolve_url(database_url)), revision)


def downgrade(database_url: str | None = None, revision: str = "-1") -> None:
    from alembic import command
    command.downgrade(_build_config(_resolve_url(database_url)), revision)


def current(database_url: str | None = None) -> None:
    from alembic import command
    command.current(_build_config(_resolve_url(database_url)))


def history(database_url: str | None = None) -> None:
    from alembic import command
    command.history(_build_config(_resolve_url(database_url)))


def heads(database_url: str | None = None) -> None:
    from alembic import command
    command.heads(_build_config(_resolve_url(database_url)))


def stamp(database_url: str | None = None, *revisions: str, purge: bool = False) -> None:
    from alembic import command
    command.stamp(_build_config(_resolve_url(database_url)), list(revisions), purge=purge)


def assert_schema_ready(database_url: str | None = None) -> None:
    """Fail if the database is not stamped at every configured Alembic head."""
    resolved_url = _resolve_url(database_url)
    cfg = _build_config(resolved_url)
    expected_heads = set(ScriptDirectory.from_config(cfg).get_heads())

    section = dict(cfg.get_section(cfg.config_ini_section, {}) or {})
    section["sqlalchemy.url"] = resolved_url
    engine = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with engine.connect() as connection:
            current_heads = set(
                MigrationContext.configure(connection).get_current_heads()
            )
    finally:
        engine.dispose()

    if current_heads == expected_heads:
        return

    missing = sorted(expected_heads - current_heads)
    unexpected = sorted(current_heads - expected_heads)
    details: list[str] = [
        "Database schema is not at the expected Alembic heads.",
        "Run `make migrate` before starting the server.",
        f"Expected heads: {sorted(expected_heads)}.",
        f"Current heads: {sorted(current_heads)}.",
    ]
    if missing:
        details.append(f"Missing heads: {missing}.")
    if unexpected:
        details.append(f"Unexpected heads: {unexpected}.")
    raise MigrationReadinessError(" ".join(details))


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    cmd = args[0] if args else "upgrade"
    rest = args[1:]

    url = _resolve_url(None)

    if cmd == "upgrade":
        upgrade(url, rest[0] if rest else "heads")
    elif cmd == "downgrade":
        downgrade(url, rest[0] if rest else "-1")
    elif cmd == "current":
        current(url)
    elif cmd == "history":
        history(url)
    elif cmd == "heads":
        heads(url)
    elif cmd == "stamp":
        purge = "--purge" in rest
        revs = [r for r in rest if r != "--purge"]
        stamp(url, *revs, purge=purge)
    else:
        print(
            f"Unknown command: {cmd!r}\n"
            "Usage: python -m ze_api.migrate [upgrade|downgrade|current|history|heads|stamp] [args]",
            file=sys.stderr,
        )
        sys.exit(1)
