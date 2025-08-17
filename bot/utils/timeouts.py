"""
Timeout store backed by Neon/PostgreSQL (asyncpg).

Schema (created on import via ensure_schema()):
  CREATE TABLE IF NOT EXISTS user_timeouts (
      user_id   BIGINT    NOT NULL,
      guild_id  BIGINT    NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      PRIMARY KEY (user_id, guild_id)
  );

Public API:
  - await ensure_schema()
  - await is_user_timed_out(user_id: int, guild_id: int) -> bool
  - await get_timeout_expiry(user_id: int, guild_id: int) -> int | None   # epoch seconds
  - await set_timeout(user_id: int, guild_id: int, minutes: int) -> None
  - await clear_timeout(user_id: int, guild_id: int) -> None
"""

from __future__ import annotations

import time
from typing import Optional

# >>> If your pool helpers are elsewhere, change this one import only <<<
from bot.db import get_pool  # must expose an initialized asyncpg.Pool


# ---- schema bootstrapping ----

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_timeouts (
    user_id    BIGINT       NOT NULL,
    guild_id   BIGINT       NOT NULL,
    expires_at TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (user_id, guild_id)
);
CREATE INDEX IF NOT EXISTS idx_user_timeouts_guild_exp
    ON user_timeouts (guild_id, expires_at);
"""

# lightweight guard to avoid racing multiple CREATEs on hot-reload
_schema_ready = False


async def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        # asyncpg executes only the first statement in .execute by default;
        # use conn.execute on each statement manually.
        for stmt in filter(None, (s.strip() for s in _SCHEMA_SQL.split(";"))):
            await conn.execute(stmt)
    _schema_ready = True


# ---- core helpers ----

async def is_user_timed_out(user_id: int, guild_id: int) -> bool:
    """
    True if (user_id, guild_id) has a non-expired row in user_timeouts.
    Auto-clears if expired.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT EXTRACT(EPOCH FROM expires_at)::BIGINT AS exp "
            "FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id,
        )
    if not row:
        return False

    exp = int(row["exp"])
    now = int(time.time())
    if exp <= now:
        await clear_timeout(user_id, guild_id)
        return False
    return True


async def get_timeout_expiry(user_id: int, guild_id: int) -> Optional[int]:
    """
    Returns the Unix epoch seconds for expiry, or None if not present.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT EXTRACT(EPOCH FROM expires_at)::BIGINT AS exp "
            "FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id,
        )
    if not row:
        return None
    return int(row["exp"])


async def set_timeout(user_id: int, guild_id: int, minutes: int) -> None:
    """
    Upsert a timeout. minutes<=0 means 'now' (you probably want clear_timeout instead).
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_timeouts (user_id, guild_id, expires_at)
            VALUES ($1, $2, NOW() + ($3::INT || ' minutes')::INTERVAL)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET expires_at = EXCLUDED.expires_at
            """,
            user_id, guild_id, max(0, int(minutes)),
        )


async def clear_timeout(user_id: int, guild_id: int) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id,
        )
