from __future__ import annotations
import time
from typing import Optional
from bot.db import get_pool  # your Neon asyncpg pool

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS user_timeouts (
        user_id    BIGINT      NOT NULL,
        guild_id   BIGINT      NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (user_id, guild_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_user_timeouts_guild_exp ON user_timeouts (guild_id, expires_at)",
]
_ready = False

async def ensure_schema() -> None:
    global _ready
    if _ready:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        for stmt in _SCHEMA:
            await conn.execute(stmt)
    _ready = True

async def is_user_timed_out(user_id: int, guild_id: int) -> bool:
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
    if exp <= int(time.time()):
        await clear_timeout(user_id, guild_id)
        return False
    return True

async def get_timeout_expiry(user_id: int, guild_id: int) -> Optional[int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT EXTRACT(EPOCH FROM expires_at)::BIGINT AS exp "
            "FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id,
        )
    return int(row["exp"]) if row else None

async def set_timeout(user_id: int, guild_id: int, minutes: int) -> None:
    minutes = max(0, int(minutes))
    pool = get_pool()
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
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM user_timeouts WHERE user_id=$1 AND guild_id=$2",
            user_id, guild_id,
        )
