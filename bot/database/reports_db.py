from __future__ import annotations

from ..db import get_pool

async def create_reports_table() -> None:
    """Create/upgrade the reports table (idempotent)."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
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
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """)
        # Forward-safe additions
        await conn.execute("""ALTER TABLE reports
          ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'open',
          ADD COLUMN IF NOT EXISTS closed_by BIGINT,
          ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS reported_count_at_creation INT
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
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    async with pool.acquire() as conn:
        # Count existing reports against this user
        count_before = await conn.fetchval(
            "SELECT COUNT(*) FROM reports WHERE reported_id = $1",
            int(reported_id),
        )
        total_reports = int(count_before) + 1

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
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reports SET status='closed', closed_by=$2, closed_at=NOW() WHERE id=$1",
            int(report_id), int(closed_by)
        )

async def get_report_count_for_user(reported_id: int) -> int:
    """Return the current total number of reports against a user."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    async with pool.acquire() as conn:
        val = await conn.fetchval(
            "SELECT COUNT(*) FROM reports WHERE reported_id = $1",
            int(reported_id),
        )
        return int(val or 0)
