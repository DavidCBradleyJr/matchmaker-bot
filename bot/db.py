# db.py
from typing import Iterable
import os
import asyncpg

_pool: asyncpg.Pool | None = None

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

ENV = os.getenv("ENV", "staging").lower()

def _resolve_dsn_from_env() -> str | None:
    """
    Prefer STAGING_DATABASE_URL when ENV starts with 'stag', else PROD_DATABASE_URL.
    Fallback to the other if the preferred one is missing.
    """
    if ENV.startswith("stag"):
        return os.getenv("STAGING_DATABASE_URL") or os.getenv("PROD_DATABASE_URL")
    return os.getenv("PROD_DATABASE_URL") or os.getenv("STAGING_DATABASE_URL")

async def init_pool_from_env() -> None:
    """Optional convenience: initialize pool using ENV + Neon URLs."""
    dsn = _resolve_dsn_from_env()
    if not dsn:
        raise RuntimeError("No STAGING_DATABASE_URL or PROD_DATABASE_URL set")
    await init_pool(dsn)

CREATE_STATS_SQL = """
CREATE TABLE IF NOT EXISTS bot_guilds (
  guild_id BIGINT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS bot_counters (
  metric TEXT PRIMARY KEY,
  value BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bot_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""

async def init_pool(dsn: str) -> None:
    """
    Initialize the global connection pool and ensure baseline tables exist.
    """
    global _pool
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4)
    async with _pool.acquire() as conn:
        await conn.execute(CREATE_SQL)
        await conn.execute(CREATE_STATS_SQL)

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
        return int(result.split()[-1])


async def stats_add_guild(guild_id: int) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bot_guilds (guild_id) VALUES ($1) ON CONFLICT DO NOTHING",
            int(guild_id),
        )

async def stats_remove_guild(guild_id: int) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM bot_guilds WHERE guild_id = $1",
            int(guild_id),
        )

async def stats_inc(metric: str, by: int = 1) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_counters(metric, value) VALUES ($1, $2)
            ON CONFLICT (metric) DO UPDATE SET value = bot_counters.value + EXCLUDED.value
            """,
            metric, int(by),
        )

async def stats_set_counter(metric: str, value: int) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_counters(metric, value) VALUES ($1, $2)
            ON CONFLICT (metric) DO UPDATE SET value = EXCLUDED.value
            """,
            metric, int(value),
        )

async def stats_set_meta(key: str, value: str) -> None:
    pool = _require_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_meta(key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key, value,
        )

async def stats_snapshot() -> dict:
    pool = _require_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              COALESCE((SELECT COUNT(*) FROM bot_guilds), 0) AS servers,
              COALESCE((SELECT value FROM bot_counters WHERE metric='ads_posted'), 0) AS ads_posted,
              COALESCE((SELECT value FROM bot_counters WHERE metric='connections_made'), 0) AS connections_made,
              COALESCE((SELECT value FROM bot_counters WHERE metric='matches_made'), 0) AS matches_made,
              COALESCE((SELECT value FROM bot_counters WHERE metric='errors'), 0) AS errors,
              COALESCE((SELECT value FROM bot_meta WHERE key='bot_start_time'), '') AS bot_start_time
            """
        )
        if not row:
            return {
                "servers": 0,
                "ads_posted": 0,
                "connections_made": 0,
                "matches_made": 0,
                "errors": 0,
                "bot_start_time": "",
            }
        d = dict(row)
        for k in ("servers", "ads_posted", "connections_made", "matches_made", "errors"):
            d[k] = int(d.get(k, 0) or 0)
        d["bot_start_time"] = str(d.get("bot_start_time", "") or "")
        return d
