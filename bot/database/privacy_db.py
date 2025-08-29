from __future__ import annotations

import asyncio
import logging
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


async def _find_owner_like_column(conn: asyncpg.Connection, table: str) -> str | None:
    """
    Inspect columns and choose the best candidate for 'ad owner' identity.
    Handles legacy drift (owner_id/poster_id/author_id/creator_id/user_id, etc).
    """
    try:
        cols = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=$1
            """,
            table,
        )
        names = {r["column_name"] for r in cols}
    except Exception:
        log.exception("Failed columns introspection for %s", table)
        return None

    preferred = ["owner_id", "poster_id", "author_id", "creator_id", "user_id"]
    for c in preferred:
        if c in names:
            return c

    heuristics = [n for n in names if any(k in n for k in ("owner", "poster", "author", "creator")) or n.endswith("_user_id")]
    heuristics = [n for n in heuristics if n not in {"ad_id", "guild_id", "channel_id", "message_id", "click_count"}]
    return heuristics[0] if heuristics else None


async def _delete_lfg_ads_for_user(conn: asyncpg.Connection, user_id: int) -> None:
    """
    Delete ads authored by the user, using column introspection.
    If no owner-like column exists, fallback to deleting ads whose ad_id appears in the user's clicks.
    """
    if not await _table_exists(conn, "lfg_ads"):
        return

    col = await _find_owner_like_column(conn, "lfg_ads")
    if col and await _column_exists(conn, "lfg_ads", col):
        try:
            await conn.execute(f"DELETE FROM public.lfg_ads WHERE {col} = $1", int(user_id))
            return
        except Exception:
            log.exception("Delete by owner-like column failed for lfg_ads.%s", col)

    # Fallback: delete ads where this user clicked (covers self-clicked ads; conservative)
    if await _table_exists(conn, "lfg_ad_clicks"):
        try:
            await conn.execute(
                "DELETE FROM public.lfg_ads WHERE ad_id IN (SELECT ad_id FROM public.lfg_ad_clicks WHERE user_id = $1)",
                int(user_id)
            )
        except Exception:
            log.exception("Fallback delete via lfg_ad_clicks failed for user_id=%s", user_id)
    else:
        log.warning("No matching column for delete on lfg_ads; tried owner-like columns and no lfg_ad_clicks table present.")


async def delete_user_data(user_id: int) -> None:
    """
    Delete data the bot stores *about this user* across known tables.

    - lfg_ads: delete authored ads (introspection for owner column). If unknown, fallback via clicks.
    - lfg_ad_clicks: delete their clicks on others' ads
    - reports: delete as reporter and as reported
    - user_timeouts: delete both as target and as creator (global)
    - user_post_cooldowns: delete their ad post cooldown state

    Each delete step is isolated so one failure doesn't abort the rest.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        # LFG: delete your ads (owner-column aware) first — clicks cascade if FK exists
        await _delete_lfg_ads_for_user(conn, int(user_id))

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
