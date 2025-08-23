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

# Cache the detected time column name across calls
_TIME_COL_NAME: Optional[str] = None


async def _get_time_col(conn) -> str:
    """
    Detect which timestamp column the table uses for the timeout:
    - preferred: 'until'
    - legacy:    'expires_at'
    If neither exists, attempt to add 'until' (DDL permitting), else raise.
    """
    global _TIME_COL_NAME
    if _TIME_COL_NAME:
        return _TIME_COL_NAME

    has_until = await conn.fetchval("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='user_timeouts' AND column_name='until'
    """)
    has_expires = await conn.fetchval("""
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='user_timeouts' AND column_name='expires_at'
    """)

    if has_until:
        _TIME_COL_NAME = "until"
        return _TIME_COL_NAME
    if has_expires:
        _TIME_COL_NAME = "expires_at"
        return _TIME_COL_NAME

    # Neither column exists — try to add 'until'
    try:
        await conn.execute(f"ALTER TABLE {TABLE_FQN} ADD COLUMN until TIMESTAMPTZ")
        _TIME_COL_NAME = "until"
        return _TIME_COL_NAME
    except InsufficientPrivilegeError:
        # We can't add the column and none exists — caller should surface a clear error
        raise RuntimeError("USER_TIMEOUTS_TIME_COLUMN_MISSING")
    except PostgresError:
        # Possible race; re-check once
        has_until = await conn.fetchval("""
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='user_timeouts' AND column_name='until'
        """)
        if has_until:
            _TIME_COL_NAME = "until"
            return _TIME_COL_NAME
        raise RuntimeError("USER_TIMEOUTS_TIME_COLUMN_MISSING")


# ---------- Schema management (self-healing, DDL-optional) ----------

async def ensure_user_timeouts_schema() -> None:
    """
    Ensure the user_timeouts table exists and has expected shape.
    Idempotent; best-effort if the role lacks DDL (we log and continue).
    Supports both 'until' and legacy 'expires_at' time columns.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        # Create minimal table if possible (no time column yet)
        try:
            await conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_FQN} (
                    guild_id BIGINT NOT NULL,
                    user_id  BIGINT NOT NULL
                )
                """
            )
        except InsufficientPrivilegeError:
            log.warning("No DDL privilege to CREATE %s; continuing with column/index checks.", TABLE_FQN)

        # Resolve which time column we have (or can add)
        try:
            time_col = await _get_time_col(conn)
        except RuntimeError as e:
            # We couldn't find or add a time column; log and return (writes will raise)
            log.error("Timeouts schema missing time column ('until'/'expires_at'): %s", e)
            return

        # Columns / constraints / defaults (safe to run multiple times)
        alter_statements = [
            # non-time columns
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS reason TEXT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_by BIGINT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ",

            # Backfill NULLs on time_col and created_at before NOT NULL
            f"UPDATE {TABLE_FQN} SET {time_col} = NOW() WHERE {time_col} IS NULL",
            f"UPDATE {TABLE_FQN} SET created_at = NOW() WHERE created_at IS NULL",

            # Enforce NOT NULLS
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN {time_col} SET NOT NULL",
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET NOT NULL",

            # Ensure default so inserts don’t rely on app providing created_at
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET DEFAULT NOW()",

            # Unique index required by ON CONFLICT (guild_id, user_id)
            "CREATE UNIQUE INDEX IF NOT EXISTS user_timeouts_guild_user_uidx "
            f"ON {TABLE_FQN} (guild_id, user_id)",
        ]
        for stmt in alter_statements:
            try:
                await conn.execute(stmt)
            except InsufficientPrivilegeError:
                log.warning("No DDL privilege for: %s", stmt)
            except PostgresError as exc:
                # Non-fatal: if the column already matches or small race, continue.
                log.debug("Postgres notice during ensure: %s: %s", type(exc).__name__, exc)


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
    If the schema/columns are missing and we cannot DDL, a clear RuntimeError is raised.
    Supports tables that use 'until' or 'expires_at' for the time column.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    # Best-effort schema ensure (no-op if role can't DDL)
    await ensure_user_timeouts_schema()

    async with pool.acquire() as conn:
        time_col = await _get_time_col(conn)

        UPSERT = f"""
            INSERT INTO {TABLE_FQN} (guild_id, user_id, {time_col}, reason, created_by, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET {time_col} = EXCLUDED.{time_col},
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
            time_col = await _get_time_col(conn)  # re-resolve in case it changed
            UPSERT = f"""
                INSERT INTO {TABLE_FQN} (guild_id, user_id, {time_col}, reason, created_by, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET {time_col} = EXCLUDED.{time_col},
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
            except (UndefinedTableError, UndefinedColumnError, InsufficientPrivilegeError):
                # Check whether the critical time column exists in 'public'
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='user_timeouts' AND column_name IN ('until','expires_at')
                    """
                )
                if not exists:
                    raise RuntimeError("USER_TIMEOUTS_TABLE_MISSING")
                raise RuntimeError("MISSING_USER_TIMEOUTS_SCHEMA_OR_DDL_PRIVS")
        except InsufficientPrivilegeError as exc:
            raise RuntimeError("DB_WRITE_INSUFFICIENT_PRIVILEGE") from exc
        except PostgresError as exc:
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
    Return the 'until' timestamp if a timeout exists, else None.
    Works whether the DB column is called 'until' or 'expires_at'.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            time_col = await _get_time_col(conn)
            row = await conn.fetchrow(
                f"SELECT {time_col} AS until FROM {TABLE_FQN} WHERE guild_id=$1 AND user_id=$2",
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
