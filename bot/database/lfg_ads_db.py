import asyncpg
from datetime import datetime
from typing import Optional, List, Dict, Any

from ..db import get_pool


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS lfg_ads (
    ad_id            SERIAL PRIMARY KEY,
    guild_id         BIGINT NOT NULL,
    channel_id       BIGINT NOT NULL,
    message_id       BIGINT NOT NULL,
    owner_id         BIGINT NOT NULL,
    game             TEXT,
    notes            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ NOT NULL,
    notify_on_expire BOOLEAN NOT NULL DEFAULT FALSE,
    expired_handled  BOOLEAN NOT NULL DEFAULT FALSE,
    click_count      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lfg_ad_clicks (
    ad_id      INTEGER REFERENCES lfg_ads(ad_id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL,
    clicked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ad_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_lfg_ads_message_id ON lfg_ads (message_id);
CREATE INDEX IF NOT EXISTS idx_lfg_ads_expires_at ON lfg_ads (expires_at);
"""


async def init_tables() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)


async def create_ad(
    guild_id: int,
    channel_id: int,
    message_id: int,
    owner_id: int,
    game: Optional[str],
    notes: Optional[str],
    expires_at: datetime,
    notify_on_expire: bool = False,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO lfg_ads (
                guild_id, channel_id, message_id, owner_id,
                game, notes, expires_at, notify_on_expire
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            RETURNING ad_id
            """,
            guild_id, channel_id, message_id, owner_id,
            game, notes, expires_at, notify_on_expire
        )
        return int(row["ad_id"])


async def get_ad_by_message_id(message_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM lfg_ads WHERE message_id=$1",
            message_id,
        )
        return dict(row) if row else None


async def record_click(ad_id: int, user_id: int) -> None:
    """Records a unique click per (ad_id, user_id). Does nothing if duplicate."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO lfg_ad_clicks (ad_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT (ad_id, user_id) DO NOTHING
                """,
                ad_id, user_id
            )
        except asyncpg.PostgresError:
            # don't raise; uniqueness is expected
            pass


async def increment_click_count(ad_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE lfg_ads SET click_count = click_count + 1 WHERE ad_id=$1",
            ad_id
        )


async def list_expired_unhandled(now: datetime) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM lfg_ads
            WHERE expires_at <= $1 AND expired_handled = FALSE
            """,
            now
        )
        return [dict(r) for r in rows]


async def mark_expired_handled(ad_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE lfg_ads SET expired_handled = TRUE WHERE ad_id=$1",
            ad_id
        )
