from __future__ import annotations

import asyncio
from typing import Any, Optional

from ..db import get_pool  # your existing pool getter (might be sync or async)

# ---------- internal: robustly obtain the pool (handles sync/async get_pool) ----------

async def _get_pool():
    """
    Returns an initialized asyncpg pool.

    Works whether your get_pool() is synchronous or asynchronous.
    Raises RuntimeError if the pool is still not initialized.
    """
    pool = get_pool()
    if asyncio.iscoroutine(pool):
        pool = await pool
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    return pool

# -------------------------------- Reports Table --------------------------------

async def create_reports_table() -> None:
    """Create/upgrade the reports & conversations tables (idempotent)."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            origin_guild_id BIGINT NOT NULL,
            reporter_id BIGINT NOT NULL,
            reported_id BIGINT NOT NULL,
            ad_id BIGINT NOT NULL,
            ad_message_id BIGINT NOT NULL,
            description TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            status TEXT DEFAULT 'open',
            closed_by BIGINT,
            closed_at TIMESTAMPTZ,
            reported_count_at_creation INT
        )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS reports_reported_created_idx "
            "ON reports (reported_id, created_at DESC)"
        )
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS report_conversations (
            report_id    INT PRIMARY KEY REFERENCES reports(id) ON DELETE CASCADE,
            reporter_id  BIGINT NOT NULL,
            channel_id   BIGINT NOT NULL,
            is_open      BOOLEAN NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_report_conversations_reporter
            ON report_conversations (reporter_id) WHERE is_open = TRUE;
        """)

async def insert_report(
    *,
    origin_guild_id: int,
    reporter_id: int,
    reported_id: int,
    ad_id: int,
    ad_message_id: int,
    description: str,
) -> tuple[int, int]:
    """
    Insert a report and return (report_id, total_reports_for_user_including_this_one).
    Also snapshots the total at creation into reported_count_at_creation.
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        count_before = await conn.fetchval(
            "SELECT COUNT(*) FROM reports WHERE reported_id = $1",
            int(reported_id),
        )
        total_reports = int(count_before or 0) + 1

        row = await conn.fetchrow(
            """
            INSERT INTO reports (
                origin_guild_id, reporter_id, reported_id, ad_id, ad_message_id,
                description, reported_count_at_creation
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, reported_count_at_creation
            """,
            int(origin_guild_id),
            int(reporter_id),
            int(reported_id),
            int(ad_id),
            int(ad_message_id),
            description,
            total_reports,
        )
        return int(row["id"]), int(row["reported_count_at_creation"])

async def close_report(report_id: int, closed_by: int) -> None:
    """Mark a report closed; no-op if id missing."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reports SET status='closed', closed_by=$2, closed_at=NOW() WHERE id=$1",
            int(report_id), int(closed_by)
        )

async def get_report_count_for_user(reported_id: int) -> int:
    """Return the current total number of reports against a user."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM reports WHERE reported_id = $1",
            int(reported_id),
        )
        return int(val or 0)

async def fetch_recent_reports_by_reported(reported_id: int, limit: int = 10):
    """Return recent reports for a user (most recent first)."""
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, origin_guild_id, reporter_id, reported_id, ad_id, ad_message_id,
                   description, status, created_at, closed_at, closed_by
            FROM reports
            WHERE reported_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            int(reported_id), int(limit),
        )
        return rows

# ------------------------------ DM conversation bridge ------------------------------

async def open_conversation(report_id: int, reporter_id: int, channel_id: int) -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO report_conversations (report_id, reporter_id, channel_id, is_open)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (report_id)
            DO UPDATE SET reporter_id = EXCLUDED.reporter_id,
                          channel_id  = EXCLUDED.channel_id,
                          is_open     = TRUE;
            """,
            int(report_id), int(reporter_id), int(channel_id)
        )

async def get_open_conversation_by_reporter(reporter_id: int) -> Optional[dict[str, Any]]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT report_id, reporter_id, channel_id
            FROM report_conversations
            WHERE reporter_id = $1 AND is_open = TRUE
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            int(reporter_id)
        )
        return dict(row) if row else None

async def close_conversation(report_id: int) -> None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE report_conversations SET is_open = FALSE WHERE report_id = $1;",
            int(report_id)
        )
