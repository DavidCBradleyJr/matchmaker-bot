from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from asyncpg import (
    UndefinedTableError,
    UndefinedColumnError,
    InsufficientPrivilegeError,
    PostgresError,
)
from ..db import get_pool

log = logging.getLogger(__name__)

TABLE_FQN = "public.user_timeouts"  # schema-qualify to avoid search_path surprises

# ---------- Schema management (self-healing, DDL-optional) ----------

async def ensure_user_timeouts_schema() -> None:
    """
    Ensure the user_timeouts table exists and has expected columns.
    - If the DB role lacks DDL, we log and continue; writes will then
      require the table/columns to already exist (via migration).
    - Safe to call repeatedly (idempotent).
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        # Try to create table (if we have DDL privileges)
        try:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_FQN} (
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
        except InsufficientPrivilegeError:
            log.warning("No DDL privilege to CREATE %s; will still attempt ALTER checks.", TABLE_FQN)

        # Try to add columns if missing (best-effort)
        for stmt in (
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS reason TEXT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_by BIGINT",
        ):
            try:
                await conn.execute(stmt)
            except InsufficientPrivilegeError:
                log.warning("No DDL privilege to ALTER %s; column ensure skipped.", TABLE_FQN)


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

    If the schema/columns are missing and we cannot DDL, a clear RuntimeError is raised.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    # Best-effort schema ensure (no-op if role can't DDL)
    await ensure_user_timeouts_schema()

    async with pool.acquire() as conn:
        UPSERT = f"""
            INSERT INTO {TABLE_FQN} (guild_id, user_id, until, reason, created_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET until = EXCLUDED.until,
                reason = EXCLUDED.reason,
                created_by = EXCLUDED.created_by
        """
        try:
            await conn.execute(
                UPSERT,
                int(guild_id),
                int(user_id),
                until,
                reason,
                created_by,
            )
        except (UndefinedTableError, UndefinedColumnError):
            # Heal (if possible) then retry once
            await ensure_user_timeouts_schema()
            try:
                await conn.execute(
                    UPSERT,
                    int(guild_id),
                    int(user_id),
                    until,
                    reason,
                    created_by,
                )
            except (UndefinedTableError, UndefinedColumnError, InsufficientPrivilegeError):
                # Double-check if the table actually exists in 'public'
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema='public' AND table_name='user_timeouts'
                    """
                )
                if not exists:
                    raise RuntimeError("USER_TIMEOUTS_TABLE_MISSING")
                raise RuntimeError("MISSING_USER_TIMEOUTS_SCHEMA_OR_DDL_PRIVS")
        except InsufficientPrivilegeError as exc:
            # INSERT itself failed because of privileges
            raise RuntimeError("DB_WRITE_INSUFFICIENT_PRIVILEGE") from exc
        except PostgresError as exc:
            # Any other asyncpg/Postgres error; surface a stable message upward
            raise RuntimeError(f"DB_WRITE_FAILED: {type(exc).__name__}") from exc


async def clear_timeout(guild_id: int, user_id: int) -> None:
    """Delete a timeout row if it exists."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                f"DELETE FROM {TABLE_FQN} WHERE guild_id=$1 AND user_id=$2",
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
                f"SELECT until FROM {TABLE_FQN} WHERE guild_id=$1 AND user_id=$2",
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
