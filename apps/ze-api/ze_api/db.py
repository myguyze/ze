import json

import asyncpg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from ze_api.settings import Settings

# LangGraph's AsyncPostgresSaver uses psycopg3, not asyncpg.
_CHECKPOINTER_CONN_KWARGS = {
    "autocommit": True,
    "prepare_threshold": 0,
    "row_factory": dict_row,
}


async def _init_conn(conn: asyncpg.Connection) -> None:
    # asyncpg 0.29+ no longer auto-decodes jsonb; register codecs explicitly.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(settings: Settings) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
        init=_init_conn,
    )
    assert pool is not None  # create_pool returns Pool | None with min_size set
    return pool


async def dispose_pool(pool: asyncpg.Pool) -> None:
    await pool.close()


async def create_checkpointer_pool(settings: Settings) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        kwargs=_CHECKPOINTER_CONN_KWARGS,
        min_size=2,
        max_size=5,
        open=False,
    )
    await pool.open()
    await pool.wait()
    return pool


async def dispose_checkpointer_pool(pool: AsyncConnectionPool) -> None:
    await pool.close()
