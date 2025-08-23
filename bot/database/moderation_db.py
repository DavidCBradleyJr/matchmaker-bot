from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from asyncpg import UndefinedTableError, UndefinedColumnError
from ..db import get_pool

log = logging.getLogger(__name__)


# ---------- Schema management (self-healing) ----------

async def ensure_user_timeouts_schema() -> None:
    """
    Ensure the user_timeouts table exists and has the columns we write/read.
    Safe to call repeatedly (idempotent).
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        # Create table if missing (with PK on (guild_id, user_id))
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_timeouts (
                guild_id   BIGINT NOT NULL,
                user_id    BIGINT NOT NULL,
                until      TIMESTAMPTZ NOT NULL,
                reason     TEXT,
                created_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        # Add columns if the table pre-existed without them
        await conn.execute("ALTER TABLE user_timeouts ADD COLUMN IF NOT EXISTS reason TEXT")
        await conn.execute("ALTER TABLE user_timeouts ADD COLUMN IF NOT EXISTS created_by BIGINT")


# ---------- Writes ----------

async def add_timeout(
    guild_id: int,
    user_id: int,
    until: datetime,
    *,
    created_by: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    """
    Upsert a timeout for (guild_id, user_id).
    - If a row exists, overwrite until/reason/created_by.
    - If not, insert a new row.

    Mirrors the UPSERT style used elsewhere in db.py (ON CONFLICT DO UPDATE).
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    # Ensure schema, then write
    await ensure_user_timeouts_schema()

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO user_timeouts (guild_id, user_id, until, reason, created_by)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET until = EXCLUDED.until,
                    reason = EXCLUDED.reason,
                    created_by = EXCLUDED.created_by
                """,
                int(guild_id),
                int(user_id),
                until,
                reason,
                created_by,
            )
        except (UndefinedTableError, UndefinedColumnError):
            # In case another process is mid-deploy, heal then retry once.
            await ensure_user_timeouts_schema()
            await conn.execute(
                """
                INSERT INTO user_timeouts (guild_id, user_id, until, reason, created_by)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET until = EXCLUDED.until,
                    reason = EXCLUDED.reason,
                    created_by = EXCLUDED.created_by
                """,
                int(guild_id),
                int(user_id),
                until,
                reason,
                created_by,
            )


async def clear_timeout(guild_id: int, user_id: int) -> None:
    """Delete a timeout row if it exists."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "DELETE FROM user_timeouts WHERE guild_id=$1 AND user_id=$2",
                int(guild_id),
                int(user_id),
            )
        except (UndefinedTableError, UndefinedColumnError):
            # Table/column missing => nothing to clear.
            return


# ---------- Reads ----------

async def get_timeout_until(guild_id: int, user_id: int) -> Optional[datetime]:
    """
    Return the 'until' timestamp if a timeout exists for the user,
    else None.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT until FROM user_timeouts WHERE guild_id=$1 AND user_id=$2",
                int(guild_id),
                int(user_id),
            )
        except (UndefinedTableError, UndefinedColumnError):
            return None
    return row["until"] if row else None


async def is_user_timed_out(guild_id: int, user_id: int, *, now: Optional[datetime] = None) -> bool:
    """
    True if the user has a timeout with until > now.
    """
    now = now or datetime.now(timezone.utc)
    until = await get_timeout_until(int(guild_id), int(user_id))
    return bool(until and until > now)
