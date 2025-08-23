from __future__ import annotations

from ..db import get_pool

async def create_reports_table() -> None:
    """Create the reports table if it doesn't exist."""
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

async def insert_report(
    *,
    origin_guild_id: int,
    reporter_id: int,
    reported_id: int,
    ad_id: int,
    ad_message_id: int,
    description: str,
) -> int:
    """Insert a report and return its id (used as the report number)."""
    pool = get_pool()
    if pool is None:
        raise RuntimeError("DB pool is not initialized.")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO reports (origin_guild_id, reporter_id, reported_id, ad_id, ad_message_id, description)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            origin_guild_id, reporter_id, reported_id, ad_id, ad_message_id, description
        )
        return int(row["id"])
