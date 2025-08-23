from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
from asyncpg import InsufficientPrivilegeError, PostgresError, UndefinedTableError, UndefinedColumnError
from ..db import get_pool

log = logging.getLogger(__name__)
TABLE_FQN = "public.user_post_cooldowns"

async def ensure_cooldowns_schema() -> None:
    pool = get_pool()
    if not pool:
        raise RuntimeError("DB pool not initialized")
    async with pool.acquire() as conn:
        try:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_FQN} (
                    user_id     BIGINT PRIMARY KEY,
                    next_ok_at  TIMESTAMPTZ NOT NULL,
                    reason      TEXT,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
        except InsufficientPrivilegeError:
            log.warning("Missing DDL privilege to CREATE %s", TABLE_FQN)
        # Ensure NOT NULL & defaults (idempotent)
        for stmt in (
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN next_ok_at SET NOT NULL",
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET NOT NULL",
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN updated_at SET NOT NULL",
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN created_at SET DEFAULT NOW()",
            f"ALTER TABLE {TABLE_FQN} ALTER COLUMN updated_at SET DEFAULT NOW()",
        ):
            try:
                await conn.execute(stmt)
            except InsufficientPrivilegeError:
                log.warning("Missing DDL privilege for: %s", stmt)
            except PostgresError:
                pass  # ignore harmless races

async def get_next_ok_at(user_id: int) -> Optional[datetime]:
    pool = get_pool()
    if not pool:
        raise RuntimeError("DB pool not initialized")
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(f"SELECT next_ok_at FROM {TABLE_FQN} WHERE user_id=$1", int(user_id))
        except (UndefinedTableError, UndefinedColumnError):
            return None
    return row["next_ok_at"] if row else None

async def set_next_ok_at(user_id: int, when: datetime, *, reason: str | None = None) -> None:
    pool = get_pool()
    if not pool:
        raise RuntimeError("DB pool not initialized")
    await ensure_cooldowns_schema()
    async with pool.acquire() as conn:
        UPSERT = f"""
            INSERT INTO {TABLE_FQN} (user_id, next_ok_at, reason, created_at, updated_at)
            VALUES ($1, $2, $3, NOW(), NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET next_ok_at = EXCLUDED.next_ok_at,
                reason     = EXCLUDED.reason,
                updated_at = NOW()
        """
        await conn.execute(UPSERT, int(user_id), when, reason)

async def clear(user_id: int) -> None:
    pool = get_pool()
    if not pool:
        raise RuntimeError("DB pool not initialized")
    async with pool.acquire() as conn:
        try:
            await conn.execute(f"DELETE FROM {TABLE_FQN} WHERE user_id=$1", int(user_id))
        except (UndefinedTableError, UndefinedColumnError):
            return
