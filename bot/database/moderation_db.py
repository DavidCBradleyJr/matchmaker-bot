from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from asyncpg import UndefinedTableError, UndefinedColumnError
from ..db import get_pool

log = logging.getLogger(__name__)


async def ensure_user_timeouts_schema() -> None:
    """
    Idempotently ensures the user_timeouts table has the columns we write to.
    Safe to run on every boot or before each write.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_timeouts (
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                until TIMESTAMPTZ NOT NULL,
                reason TEXT,
                created_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )



async def add_timeout(
    guild_id: int,
    user_id: int,
    until: datetime,
    *,
    created_by: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    """
    Create or update a timeout for (guild_id, user_id).
    - If a row exists, we UPDATE fields.
    - Otherwise we INSERT a new row.

    We explicitly list columns, so schema drift is less likely to break us.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    # Self-heal the schema before attempting the write
    await ensure_user_timeouts_schema()

    async with pool.acquire() as conn:
        try:
            status: str = await conn.execute(
                """
                UPDATE user_timeouts
                SET until=$3, reason=$4, created_by=$5
                WHERE guild_id=$1 AND user_id=$2
                """,
                guild_id,
                user_id,
                until,
                reason,
                created_by,
            )
            # asyncpg returns e.g. "UPDATE 0" if nothing matched
            if status.split()[-1] == "0":
                await conn.execute(
                    """
                    INSERT INTO user_timeouts (guild_id, user_id, until, reason, created_by)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    guild_id,
                    user_id,
                    until,
                    reason,
                    created_by,
                )

        except (UndefinedTableError, UndefinedColumnError):
            # Last-resort heal+retry if another process created an older version of the table mid-deploy
            await ensure_user_timeouts_schema()
            await conn.execute(
                """
                UPDATE user_timeouts
                SET until=$3, reason=$4, created_by=$5
                WHERE guild_id=$1 AND user_id=$2
                """,
                guild_id,
                user_id,
                until,
                reason,
                created_by,
            )
            # If still no row, insert
            status = await conn.execute(
                "SELECT 1 FROM user_timeouts WHERE guild_id=$1 AND user_id=$2",
                guild_id,
                user_id,
            )
            if not status:
                await conn.execute(
                    """
                    INSERT INTO user_timeouts (guild_id, user_id, until, reason, created_by)
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    guild_id,
                    user_id,
                    until,
                    reason,
                    created_by,
                )


async def clear_timeout(guild_id: int, user_id: int) -> None:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "DELETE FROM user_timeouts WHERE guild_id=$1 AND user_id=$2",
                guild_id,
                user_id,
            )
        except (UndefinedTableError, UndefinedColumnError):
            # If table/columns don't exist, there's nothing to clear.
            return


async def get_timeout_until(guild_id: int, user_id: int) -> Optional[datetime]:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT until FROM user_timeouts WHERE guild_id=$1 AND user_id=$2",
                guild_id,
                user_id,
            )
        except (UndefinedTableError, UndefinedColumnError):
            return None

    return row["until"] if row else None


async def is_user_timed_out(guild_id: int, user_id: int, *, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = await get_timeout_until(guild_id, user_id)
    return bool(until and until > now)
