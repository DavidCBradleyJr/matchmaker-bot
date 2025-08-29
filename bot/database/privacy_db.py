from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg
from ..db import get_pool

log = logging.getLogger(__name__)


async def _get_pool() -> asyncpg.Pool:
    pool = get_pool()
    if asyncio.iscoroutine(pool):
        pool = await pool
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    return pool


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    """Return True if public.{table} exists."""
    fqn = f"public.{table}"
    try:
        exists = await conn.fetchval("SELECT to_regclass($1)", fqn)
        return bool(exists)
    except Exception:
        log.exception("Failed table existence check for %s", fqn)
        return False


async def _column_exists(conn: asyncpg.Connection, table: str, column: str) -> bool:
    """Return True if column exists on public.{table}."""
    try:
        return bool(
            await conn.fetchval(
                """
                SELECT 1
                FROM   pg_attribute a
                JOIN   pg_class c ON a.attrelid = c.oid
                JOIN   pg_namespace n ON c.relnamespace = n.oid
                WHERE  n.nspname = 'public'
                  AND  c.relname = $1
                  AND  a.attname = $2
                  AND  a.attnum > 0
                  AND  NOT a.attisdropped
                LIMIT 1
                """,
                table, column
            )
        )
    except Exception:
        log.exception("Failed column existence check for %s.%s", table, column)
        return False


async def _safe_delete(conn: asyncpg.Connection, table: str, where_sql: str, *params: object) -> None:
    """
    If the table exists, run a parameterized DELETE with the provided WHERE fragment.
    Example: _safe_delete(conn, "user_timeouts", "user_id = $1", user_id)
    """
    try:
        if await _table_exists(conn, table):
            sql = f"DELETE FROM public.{table} WHERE {where_sql}"
            await conn.execute(sql, *params)
    except Exception:
        log.exception("Privacy delete failed for table=%s where=%s params=%s", table, where_sql, params)


async def _delete_by_first_existing_column(conn, table: str, candidate_cols: list[str], user_id: int) -> None:
    """
    For tables with historical column name drift (e.g., lfg_ads.owner_id vs poster_id),
    find the first column that exists and delete by it.
    """
    try:
        if not await _table_exists(conn, table):
            return
        for col in candidate_cols:
            if await _column_exists(conn, table, col):
                await conn.execute(f"DELETE FROM public.{table} WHERE {col} = $1", int(user_id))
                return
        # If none of the columns exist, do nothing (schema mismatch)
        log.warning("No matching column for delete on %s; tried %s", table, candidate_cols)
    except Exception:
        log.exception("Column-aware delete failed for table=%s candidates=%s", table, candidate_cols)


async def delete_user_data(user_id: int) -> None:
    """
    Delete data the bot stores *about this user* across known tables.

    - lfg_ads (owner_id|poster_id|user_id): removes the user's ads; clicks cascade via FK
    - lfg_ad_clicks (user_id): removes their clicks on others' ads
    - reports (reporter_id / reported_id): removes their reports and reports about them
    - user_timeouts (user_id / created_by): removes timeouts on them and ones they created
    - user_post_cooldowns (user_id): removes their ad post cooldown state

    Each delete is isolated so one failure doesn't abort the rest.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        # LFG: your ads (cascades clicks via FK); support legacy column names
        await _delete_by_first_existing_column(conn, "lfg_ads", ["owner_id", "poster_id", "user_id"], int(user_id))
        # Your clicks on others' ads
        await _safe_delete(conn, "lfg_ad_clicks", "user_id = $1", int(user_id))

        # Reports you filed / reports about you
        await _safe_delete(conn, "reports", "reporter_id = $1", int(user_id))
        await _safe_delete(conn, "reports", "reported_id = $1", int(user_id))

        # Moderation timeouts
        await _safe_delete(conn, "user_timeouts", "user_id = $1", int(user_id))
        await _safe_delete(conn, "user_timeouts", "created_by = $1", int(user_id))

        # Post cooldowns
        await _safe_delete(conn, "user_post_cooldowns", "user_id = $1", int(user_id))
