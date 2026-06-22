import importlib
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def load_sql(package: str, relative_path: str) -> str:
    """Load a SQL file from an installed package's migrations/ directory.

    Usage in a migration version file::

        from migrations.env import load_sql
        def upgrade() -> None:
            op.execute(load_sql("ze_personal", "migrations/001_contacts.sql"))

    This keeps schema ownership with the domain package. Revisions live in each
    owning package's migrations/versions/ directory; ze-api is the deployment
    runner only (see ze_api.migrate).
    """
    mod = importlib.import_module(package)
    base = Path(mod.__file__).parent
    return (base / relative_path).read_text()

# No ORM models — raw SQL migrations via op.execute()
target_metadata = None

def get_url() -> str:
    # Prefer DATABASE_URL_SYNC env var; fall back to alembic.ini sqlalchemy.url
    return os.environ.get("DATABASE_URL_SYNC", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
