import asyncpg

from ze.settings import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    assert pool is not None  # create_pool returns Pool | None with min_size set
    return pool


async def dispose_pool(pool: asyncpg.Pool) -> None:
    await pool.close()
