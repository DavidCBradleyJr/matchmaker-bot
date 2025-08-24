from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from asyncpg import UndefinedTableError, UndefinedColumnError
from ..db import get_pool

log = logging.getLogger(__name__)

TABLE_FQN = "public.user_timeouts"

# ---------- Schema ----------

async def ensure_user_timeouts_schema() -> None:
    """
    Create/repair the user_timeouts table and supporting indexes if they don't exist.
    Also relax legacy NOT NULL on expires_at so inserts that only set `until` don't fail.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        # Create table if missing
        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_FQN} (
                guild_id    BIGINT,
                user_id     BIGINT,
                until       TIMESTAMPTZ,
                expires_at  TIMESTAMPTZ,
                reason      TEXT,
                created_by  BIGINT,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        # Ensure columns exist (idempotent, handles legacy shells)
        await conn.execute(
            f"""
            ALTER TABLE {TABLE_FQN}
              ADD COLUMN IF NOT EXISTS guild_id   BIGINT,
              ADD COLUMN IF NOT EXISTS user_id    BIGINT,
              ADD COLUMN IF NOT EXISTS until      TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
              ADD COLUMN IF NOT EXISTS reason     TEXT,
              ADD COLUMN IF NOT EXISTS created_by BIGINT,
              ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
            """
        )
        # ✅ Some databases had expires_at NOT NULL — relax it
        try:
            await conn.execute(f"ALTER TABLE {TABLE_FQN} ALTER COLUMN expires_at DROP NOT NULL;")
        except Exception:
            # harmless if already nullable
            pass

        # Uniqueness for upsert behavior
        await conn.execute(
            f"""
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                 WHERE schemaname = 'public' AND tablename = 'user_timeouts'
                   AND indexname = 'idx_user_timeouts_guild_user'
              ) THEN
                CREATE UNIQUE INDEX idx_user_timeouts_guild_user
                  ON {TABLE_FQN} (guild_id, user_id);
              END IF;
            END$$;
            """
        )

        # Helpful indexes
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_user_timeouts_until ON {TABLE_FQN} (until DESC NULLS LAST);")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_user_timeouts_expires_at ON {TABLE_FQN} (expires_at DESC NULLS LAST);")
        await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_user_timeouts_user_until ON {TABLE_FQN} (user_id, until DESC NULLS LAST);")

# ---------- Mutations ----------

async def add_timeout(
    guild_id: int,
    user_id: int,
    until: datetime,
    *,
    created_by: Optional[int] = None,
    reason: Optional[str] = None,
) -> None:
    """
    Upsert a timeout for (guild_id, user_id). We mirror `expires_at = until`
    for compatibility with older schemas that required expires_at NOT NULL.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")

    async with pool.acquire() as conn:
        try:
            await conn.execute(
                f"""
                INSERT INTO {TABLE_FQN} (guild_id, user_id, until, expires_at, reason, created_by, created_at)
                VALUES ($1, $2, $3, $3, $4, $5, NOW())
                ON CONFLICT (guild_id, user_id)
                DO UPDATE SET
                  until      = EXCLUDED.until,
                  expires_at = EXCLUDED.expires_at,
                  reason     = EXCLUDED.reason,
                  created_by = EXCLUDED.created_by,
                  created_at = NOW();
                """,
                int(guild_id), int(user_id), until, reason, created_by
            )
        except (UndefinedTableError, UndefinedColumnError):
            # Attempt to self-heal the schema once, then retry
            await ensure_user_timeouts_schema()
            await conn.execute(
                f"""
                INSERT INTO {TABLE_FQN} (guild_id, user_id, until, expires_at, reason, created_by, created_at)
                VALUES ($1, $2, $3, $3, $4, $5, NOW())
                ON CONFLICT (guild_id, user_id)
                DO UPDATE SET
                  until      = EXCLUDED.until,
                  expires_at = EXCLUDED.expires_at,
                  reason     = EXCLUDED.reason,
                  created_by = EXCLUDED.created_by,
                  created_at = NOW();
                """,
                int(guild_id), int(user_id), until, reason, created_by
            )
        except Exception:
            log.exception("add_timeout failed (guild=%s user=%s)", guild_id, user_id)
            raise

# ---------- Reads (per-guild) ----------

async def get_timeout_until(guild_id: int, user_id: int) -> Optional[datetime]:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                f"SELECT COALESCE(until, expires_at) AS until FROM {TABLE_FQN} WHERE guild_id = $1 AND user_id = $2",
                int(guild_id), int(user_id),
            )
        except (UndefinedTableError, UndefinedColumnError):
            return None
    return row["until"] if row else None

async def is_user_timed_out(guild_id: int, user_id: int, *, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = await get_timeout_until(int(guild_id), int(user_id))
    return bool(until and until > now)

# ---------- Reads (GLOBAL) ----------

async def get_global_timeout_until(user_id: int, *, now: Optional[datetime] = None) -> Optional[datetime]:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized; check DATABASE_URL and pool init in main().")
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                f"SELECT MAX(COALESCE(until, expires_at)) AS until FROM {TABLE_FQN} WHERE user_id = $1",
                int(user_id),
            )
        except (UndefinedTableError, UndefinedColumnError):
            return None
    return row["until"] if row and row["until"] else None

async def is_user_globally_timed_out(user_id: int, *, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    until = await get_global_timeout_until(int(user_id), now=now)
    return bool(until and until > now)
