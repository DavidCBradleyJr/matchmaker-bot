from __future__ import annotations

import os
import time
import sqlite3
import asyncio
from typing import Optional

_DB_PATH = os.getenv("TIMEOUT_DB_PATH", "/app/data/timeouts.sqlite")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, isolation_level=None, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timeouts (
            user_id   INTEGER NOT NULL,
            guild_id  INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            PRIMARY KEY (user_id, guild_id)
        )
        """
    )
    return conn


_CONN = _connect()
_LOCK = asyncio.Lock()


async def is_user_timed_out(user_id: int, guild_id: int) -> bool:
    async with _LOCK:
        cur = _CONN.execute(
            "SELECT expires_at FROM timeouts WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        )
        row = cur.fetchone()
    if not row:
        return False
    expires_at = int(row[0])
    now = int(time.time())
    if expires_at <= now:
        # auto-clear expired rows
        await clear_timeout(user_id, guild_id)
        return False
    return True


async def get_timeout_expiry(user_id: int, guild_id: int) -> Optional[int]:
    async with _LOCK:
        cur = _CONN.execute(
            "SELECT expires_at FROM timeouts WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    return int(row[0])


async def set_timeout(user_id: int, guild_id: int, minutes: int) -> None:
    expires_at = int(time.time()) + max(0, minutes) * 60
    async with _LOCK:
        _CONN.execute(
            "INSERT INTO timeouts(user_id, guild_id, expires_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET expires_at=excluded.expires_at",
            (user_id, guild_id, expires_at),
        )


async def clear_timeout(user_id: int, guild_id: int) -> None:
    async with _LOCK:
        _CONN.execute(
            "DELETE FROM timeouts WHERE user_id=? AND guild_id=?",
            (user_id, guild_id),
        )
