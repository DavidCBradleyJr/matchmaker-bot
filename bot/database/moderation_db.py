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
    Ensure the user_timeouts table exists and has expected shape.
    Idempotent; best-effort if the role lacks DDL (we log and continue).
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        # Create (columns minimal) if we can
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
            log.warning("No DDL privilege to CREATE %s; attempting column/index checks anyway.", TABLE_FQN)

        # Columns (add if missing)
        alter_statements = [
            # add core columns if missing
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS until TIMESTAMPTZ",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS reason TEXT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_by BIGINT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ",
            # backfill NULLs to satisfy NOT NULLs
            f"UPDATE {TABLE_FQN} SET until = NOW() WHERE until IS NULL",
            f"UPDATE {TABLE_FQN} SET created_at = NOW() WHERE created_at IS NULL",
            # enforce NOT NULL where expected
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN until SET NOT NULL",
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET NOT NULL",
            # ensure unique index for ON CONFLICT (guild_id,user_id)
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
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='public' AND table_name='user_timeouts' AND column_name='until'
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
            return


# ---------- Reads ----------

async def get_timeout_until(guild_id: int, user_id: int) -> Optional[datetime]:
    """Return the 'until' timestamp if a timeout exists, else None."""
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
    """True if the user has a timeout with until > now."""
    now = now or datetime.now(timezone.utc)
    until = await get_timeout_until(int(guild_id), int(user_id))
    return bool(until and until > now)
