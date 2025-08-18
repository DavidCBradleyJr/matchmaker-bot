from typing import Iterable
import asyncpg

]_pool: asyncpg.Pool | None = None

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS allowed_guilds (
  id BIGINT PRIMARY KEY,
  environment TEXT NOT NULL
)
"""

def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool

async def init_pool(dsn: str) -> None:
    """
    Initialize the global connection pool and ensure baseline tables exist.
    """
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    async with _pool.acquire() as conn:
        await conn.execute(CREATE_SQL)

def get_pool() -> asyncpg.Pool:
    """Access the initialized pool (used by cogs that need raw queries)."""
    return _require_pool()

# -------- allowlist helpers (staging gate) --------

async def get_allowed_guilds(environment: str) -> set[int]:
    pool = _require_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM allowed_guilds WHERE environment = $1",
            environment,
        )
        return {int(r["id"]) for r in rows}

async def add_allowed_guilds(environment: str, guild_ids: Iterable[int]) -> int:
    pool = _require_pool()
    q = """
        INSERT INTO allowed_guilds (id, environment)
        VALUES ($1, $2)
        ON CONFLICT (id) DO UPDATE
        SET environment = EXCLUDED.environment
    """
    count = 0
    async with pool.acquire() as conn:
        for gid in guild_ids:
            await conn.execute(q, int(gid), environment)
            count += 1
    return count

async def remove_allowed_guilds(environment: str, guild_ids: Iterable[int]) -> int:
    pool = _require_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM allowed_guilds WHERE environment = $1 AND id = ANY($2::BIGINT[])",
            environment,
            list(map(int, guild_ids)),
        )
        # result is like "DELETE 2"
        return int(result.split()[-1])
