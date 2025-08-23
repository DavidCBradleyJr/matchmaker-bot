from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict

from asyncpg import (
    UndefinedTableError,
    UndefinedColumnError,
    InsufficientPrivilegeError,
    PostgresError,
)
from ..db import get_pool

log = logging.getLogger(__name__)

TABLE_FQN = "public.user_timeouts"  # schema-qualify to avoid search_path surprises


# -------- helpers --------

async def _detect_time_cols(conn) -> Dict[str, bool]:
    """
    Return which time columns exist on the table.
    We support either/both of:
      - 'until' (preferred new name)
      - 'expires_at' (legacy)
    """
    row = await conn.fetchrow("""
        SELECT
          EXISTS(SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='user_timeouts' AND column_name='until')      AS has_until,
          EXISTS(SELECT 1 FROM information_schema.columns
                 WHERE table_schema='public' AND table_name='user_timeouts' AND column_name='expires_at') AS has_expires
    """)
    return {"has_until": bool(row["has_until"]), "has_expires": bool(row["has_expires"])}


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
        # Create minimal table if we can
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

        # Try to add both time columns as needed (we prefer 'until', but we won't remove 'expires_at')
        for stmt in (
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS until TIMESTAMPTZ",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS reason TEXT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_by BIGINT",
            f"ALTER TABLE {TABLE_FQN} ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ",
        ):
            try:
                await conn.execute(stmt)
            except InsufficientPrivilegeError:
                log.warning("No DDL privilege for: %s", stmt)
            except PostgresError as exc:
                log.debug("Postgres notice during ensure: %s: %s", type(exc).__name__, exc)

        # Backfill and constraints/defaults
        cols = await _detect_time_cols(conn)
        has_until = cols["has_until"]
        has_expires = cols["has_expires"]

        # If both are present, normalize values so neither is NULL
        try:
            if has_until and has_expires:
                await conn.execute(f"UPDATE {TABLE_FQN} SET expires_at = until WHERE expires_at IS NULL AND until IS NOT NULL")
                await conn.execute(f"UPDATE {TABLE_FQN} SET until = expires_at WHERE until IS NULL AND expires_at IS NOT NULL")
            elif has_until:
                await conn.execute(f"UPDATE {TABLE_FQN} SET until = NOW() WHERE until IS NULL")
            elif has_expires:
                await conn.execute(f"UPDATE {TABLE_FQN} SET expires_at = NOW() WHERE expires_at IS NULL")
        except PostgresError as exc:
            log.debug("Backfill notice: %s: %s", type(exc).__name__, exc)

        # created_at backfill + default
        try:
            await conn.execute(f"UPDATE {TABLE_FQN} SET created_at = NOW() WHERE created_at IS NULL")
            await conn.execute(f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET NOT NULL")
            await conn.execute(f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET DEFAULT NOW()")
        except InsufficientPrivilegeError:
            log.warning("No DDL privilege to set created_at default/NOT NULL.")
        except PostgresError as exc:
            log.debug("created_at ensure notice: %s: %s", type(exc).__name__, exc)

        # Enforce NOT NULL on whichever time columns exist
        try:
            if has_until:
                await conn.execute(f"ALTER TABLE {TABLE_FQN} ALTER COLUMN until SET NOT NULL")
            if has_expires:
                await conn.execute(f"ALTER TABLE {TABLE_FQN} ALTER COLUMN expires_at SET NOT NULL")
        except InsufficientPrivilegeError:
            log.warning("No DDL privilege to set NOT NULL on time column(s).")
        except PostgresError as exc:
            log.debug("Time column NOT NULL ensure notice: %s: %s", type(exc).__name__, exc)

        # Unique index for ON CONFLICT
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS user_timeouts_guild_user_uidx "
                f"ON {TABLE_FQN} (guild_id, user_id)"
            )
        except InsufficientPrivilegeError:
            log.warning("No DDL privilege to create unique index (guild_id,user_id).")
        except PostgresError as exc:
            log.debug("Unique index ensure notice: %s: %s", type(exc).__name__, exc)


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
    Works whether the table uses 'until', 'expires_at', or both.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    # Best-effort schema ensure (no-op if role can't DDL)
    await ensure_user_timeouts_schema()

    async with pool.acquire() as conn:
        cols = await _detect_time_cols(conn)
        has_until = cols["has_until"]
        has_expires = cols["has_expires"]

        if not (has_until or has_expires):
            # Neither column exists and we couldn't add it (no DDL)
            raise RuntimeError("USER_TIMEOUTS_TIME_COLUMN_MISSING")

        # Build dynamic INSERT ... ON CONFLICT with whichever time columns exist
        insert_cols = ["guild_id", "user_id"]
        placeholders = ["$1", "$2"]
        params = [int(guild_id), int(user_id)]
        p = 3

        # time columns: if both exist, write both to avoid NOT NULL violations
        if has_until:
            insert_cols.append("until")
            placeholders.append(f"${p}")
            params.append(until)
            p += 1
        if has_expires:
            insert_cols.append("expires_at")
            placeholders.append(f"${p}")
            params.append(until)  # same value
            p += 1

        insert_cols += ["reason", "created_by", "created_at"]
        placeholders += [f"${p}", f"${p+1}", "NOW()"]
        params += [reason, created_by]

        set_parts = []
        if has_until:
            set_parts.append("until = EXCLUDED.until")
        if has_expires:
            set_parts.append("expires_at = EXCLUDED.expires_at")
        set_parts.append("reason = EXCLUDED.reason")
        set_parts.append("created_by = EXCLUDED.created_by")

        UPSERT = f"""
            INSERT INTO {TABLE_FQN} ({', '.join(insert_cols)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT (guild_id, user_id) DO UPDATE
            SET {', '.join(set_parts)}
        """

        try:
            await conn.execute(UPSERT, *params)
        except (UndefinedTableError, UndefinedColumnError):
            # Heal (if possible) then retry once
            await ensure_user_timeouts_schema()
            cols = await _detect_time_cols(conn)
            has_until = cols["has_until"]
            has_expires = cols["has_expires"]
            if not (has_until or has_expires):
                raise RuntimeError("USER_TIMEOUTS_TABLE_MISSING")

            # rebuild with current columns
            insert_cols = ["guild_id", "user_id"]
            placeholders = ["$1", "$2"]
            params = [int(guild_id), int(user_id)]
            p = 3
            if has_until:
                insert_cols.append("until")
                placeholders.append(f"${p}")
                params.append(until)
                p += 1
            if has_expires:
                insert_cols.append("expires_at")
                placeholders.append(f"${p}")
                params.append(until)
                p += 1
            insert_cols += ["reason", "created_by", "created_at"]
            placeholders += [f"${p}", f"${p+1}", "NOW()"]
            params += [reason, created_by]

            set_parts = []
            if has_until:
                set_parts.append("until = EXCLUDED.until")
            if has_expires:
                set_parts.append("expires_at = EXCLUDED.expires_at")
            set_parts.append("reason = EXCLUDED.reason")
            set_parts.append("created_by = EXCLUDED.created_by")

            UPSERT = f"""
                INSERT INTO {TABLE_FQN} ({', '.join(insert_cols)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (guild_id, user_id) DO UPDATE
                SET {', '.join(set_parts)}
            """

            try:
                await conn.execute(UPSERT, *params)
            except (UndefinedTableError, UndefinedColumnError, InsufficientPrivilegeError):
                raise RuntimeError("MISSING_USER_TIMEOUTS_SCHEMA_OR_DDL_PRIVS")
        except InsufficientPrivilegeError as exc:
            raise RuntimeError("DB_WRITE_INSUFFICIENT_PRIVILEGE") from exc
        except PostgresError as exc:
            raise RuntimeError(f"DB_WRITE_FAILED: {type(exc).__name__}") from exc


# ---------- Reads ----------

async def get_timeout_until(guild_id: int, user_id: int) -> Optional[datetime]:
    """
    Return the timeout timestamp if it exists, regardless of column name.
    Uses COALESCE(until, expires_at) for compatibility.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                f"SELECT COALESCE(until, expires_at) AS until FROM {TABLE_FQN} WHERE guild_id=$1 AND user_id=$2",
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
