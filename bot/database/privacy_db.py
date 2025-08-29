from __future__ import annotations

import asyncio
import logging
from typing import Optional

import asyncpg
from ..db import get_pool

log = logging.getLogger(__name__)


async def _get_pool() -> asyncpg.Pool:
    """
    Mirrors your modules that tolerate get_pool being sync or async.
    """
    pool = get_pool()
    if asyncio.iscoroutine(pool):
        pool = await pool
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    return pool


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    """
    Return True if public.{table} exists.
    """
    fqn = f"public.{table}"
    try:
        exists = await conn.fetchval("SELECT to_regclass($1)", fqn)
        return bool(exists)
    except Exception:
        log.exception("Failed table existence check for %s", fqn)
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


async def delete_user_data(user_id: int) -> None:
    """
    Delete data the bot stores *about this user* across known tables.

    - lfg_ads (owner): removes the user's ads; clicks cascade via FK (see lfg_ads_db schema)
    - lfg_ad_clicks (user_id): removes their clicks on others' ads
    - reports (reporter_id / reported_id): removes their reports and reports about them
    - user_timeouts (user_id / created_by): removes timeouts on them and ones they created
    - user_post_cooldowns (user_id): removes their ad post cooldown state

    All steps are best-effort and resilient to missing tables.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn, conn.transaction():
        # LFG: your ads (owner) — cascades to lfg_ad_clicks via FK
        await _safe_delete(conn, "lfg_ads", "owner_id = $1", int(user_id))
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
