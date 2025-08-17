# bot/utils/timeouts.py
"""
Neon/Postgres-backed timeouts with asyncpg using your existing DB pool.

Schema:
  CREATE TABLE IF NOT EXISTS user_timeouts (
      user_id    BIGINT      NOT NULL,
      guild_id   BIGINT      NOT NULL,
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

# Your repo already defines the asyncpg pool in bot/db.py.
# We support either get_pool() or a module-level pool attribute to match your code.
try:
    from bot.db import get_pool  # preferred
except Exception:
    get_pool = None  # type: ignore

try:
    # Fallback: some repos expose `pool` directly
    from bot import db as _dbmod  # type: ignore
except Exception:
    _dbmod = None  # type: ignore


def _pool():
    if get_pool is not None:
        return get_pool()
    if _dbmod is not None and hasattr(_dbmod, "pool") and _dbmod.pool is not None:
        return _dbmod.pool
    raise RuntimeError("DB pool not initialized. Ensure bot/db.py created the asyncpg pool before loading cogs.")


_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS user_timeouts (
        user_id    BIGINT      NOT NULL,
        guild_id   BIGINT      NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (user_id, guild_id)
    )
    """,
    # Helpful index for dashboards/maintenance; harmless if unused
    "CREATE INDEX IF NOT EXISTS idx_user_timeouts_guild_exp ON user_timeouts (guild_id, expires_at)",
]

_schema_ready = False


async def ensure_schema() -> None:
    """Create the table/index once. Safe to call multiple times."""
    global _schema_ready
    if _schema_ready:
        return
    pool = _pool()
    async with pool.acquire() as conn:
        for stmt in _SCHEMA_SQL:
            await conn.execute(stmt)
    _schema_ready = True


async def is_user_timed_out(user_id: int, guild_id: int) -> bool:
    """
    True if a non-expired timeout exists. Auto-clears if expired.
    """
    pool = _pool()
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
    pool = _pool()
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
    Upsert timeout to NOW + minutes.
    """
    minutes = max(0, int(minutes))
    pool = _pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_timeouts (user_id, guild_id, expires_at)
            VALUES ($1, $2, NOW() + ($3::INT || ' minutes')::INTERVAL)
            ON CONFLICT (user_id, guild_id)
            DO UPDATE SET expires_at = EXCLUDED.expires_at
            """,
            user_id, guild_id, minutes,
        )


async def clear_timeout(user_id: int, guild_id: int) -> None:
    pool = _pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id,
        )
