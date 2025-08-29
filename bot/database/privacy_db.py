from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg
from ..db import get_pool  # matches your other DB modules

log = logging.getLogger(__name__)

async def _get_pool() -> asyncpg.Pool:
    """
    Mirrors reports_db.py behavior: tolerate either a direct pool or a coroutine
    returning a pool; raise if uninitialized.  (Matches your mixed usage.)
    """
    pool = get_pool()
    if asyncio.iscoroutine(pool):
        pool = await pool
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    return pool

async def _may_delete(conn: asyncpg.Connection, table: str, where_sql: str, value: int) -> None:
    """
    Delete from `table` where `where_sql` matches, but only if the table exists.
    Uses to_regclass to avoid throwing when tables haven't been created yet.
    """
    try:
        # Use a dynamic EXECUTE with USING to keep parameters safe.
        sql = f"""
        DO $$
        DECLARE
            q text;
        BEGIN
            IF to_regclass('public.{table}') IS NOT NULL THEN
                q := 'DELETE FROM public.{table} WHERE {where_sql.replace("$1", "$1")}';
                EXECUTE q USING $1;
            END IF;
        END $$;
        """
        await conn.execute(sql, int(value))
    except Exception:
        log.exception("Privacy delete failed for table=%s where=%s value=%s", table, where_sql, value)

async def delete_user_data(user_id: int) -> None:
    """
    Delete data the bot stores *about this user* across known tables.
    - lfg_ads (owner): removes the user's ads; clicks cascade via FK (lfg_ads_db)
    - lfg_ad_clicks (user_id): removes their clicks on others' ads
    - reports (reporter_id / reported_id): removes their reports and reports about them
    - user_timeouts (user_id / created_by): removes timeouts on them and ones they created
    - user_post_cooldowns (user_id): removes their ad post cooldown state
    All steps are best-effort and resilient to missing tables.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # LFG: your ads (owner) — cascades to lfg_ad_clicks via FK
            await _may_delete(conn, "lfg_ads", "owner_id = $1", user_id)
            # Your clicks on others' ads
            await _may_delete(conn, "lfg_ad_clicks", "user_id = $1", user_id)

            # Reports you filed / were filed about you
            await _may_delete(conn, "reports", "reporter_id = $1", user_id)
            await _may_delete(conn, "reports", "reported_id = $1", user_id)

            # Moderation timeouts
            await _may_delete(conn, "user_timeouts", "user_id = $1", user_id)
            await _may_delete(conn, "user_timeouts", "created_by = $1", user_id)

            # Post cooldowns
            await _may_delete(conn, "user_post_cooldowns", "user_id = $1", user_id)
