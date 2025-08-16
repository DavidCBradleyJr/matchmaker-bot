# bot/db.py
import asyncpg
from typing import Iterable

POOL: asyncpg.Pool | None = None

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS allowed_guilds (
  id BIGINT PRIMARY KEY,
  environment TEXT NOT NULL
);
"""

async def init_pool(dsn: str):
    global POOL
    POOL = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
    async with POOL.acquire() as conn:
        await conn.execute(CREATE_SQL)

async def get_allowed_guilds(environment: str) -> set[int]:
    if not POOL:
        return set()
    async with POOL.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM allowed_guilds WHERE environment = $1", environment)
        return {int(r["id"]) for r in rows}

async def add_allowed_guilds(environment: str, guild_ids: Iterable[int]) -> int:
    if not POOL:
        return 0
    q = "INSERT INTO allowed_guilds (id, environment) VALUES ($1, $2) ON CONFLICT (id) DO UPDATE SET environment = EXCLUDED.environment"
    async with POOL.acquire() as conn:
        count = 0
        for gid in guild_ids:
            await conn.execute(q, int(gid), environment)
            count += 1
        return count

async def remove_allowed_guilds(environment: str, guild_ids: Iterable[int]) -> int:
    if not POOL:
        return 0
    async with POOL.acquire() as conn:
        result = await conn.execute("DELETE FROM allowed_guilds WHERE environment = $1 AND id = ANY($2::BIGINT[])", environment, list(map(int, guild_ids)))
        # result like "DELETE 2" → extract affected rows
        return int(result.split()[-1])
