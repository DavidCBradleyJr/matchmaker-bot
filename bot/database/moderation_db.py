from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ..db import get_pool

async def create_timeouts_table() -> None:
    """Ensure the user_timeouts table exists."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_timeouts (
            user_id BIGINT PRIMARY KEY,
            reason TEXT,
            expires_at TIMESTAMPTZ NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by BIGINT
        )
        """)

async def add_timeout(user_id: int, *, minutes: int | None, reason: str, created_by: int) -> None:
    """Create or update a timeout. minutes=None means indefinite."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    expires = None
    if minutes and minutes > 0:
        expires = datetime.now(tz=timezone.utc) + timedelta(minutes=int(minutes))
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_timeouts (user_id, reason, expires_at, created_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
            SET reason=EXCLUDED.reason,
                expires_at=EXCLUDED.expires_at,
                created_at=NOW(),
                created_by=EXCLUDED.created_by
        """, int(user_id), reason, expires, int(created_by))
