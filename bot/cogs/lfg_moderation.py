from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

from ..db import get_pool

log = logging.getLogger("lfg_moderation")

# -------------------- Bootstrap (idempotent) --------------------

BOOTSTRAP_SQL = """
CREATE TABLE IF NOT EXISTS mod_settings (
  guild_id BIGINT PRIMARY KEY,
  report_category_id BIGINT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
  CREATE TYPE enforcement_status AS ENUM ('ok','timeout','banned');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS user_enforcement (
  guild_id BIGINT NOT NULL,
  user_id  BIGINT NOT NULL,
  status   enforcement_status NOT NULL,
  "until"  TIMESTAMPTZ,
  reason   TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (guild_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_enforcement_guild_status
  ON user_enforcement (guild_id, status, "until");
"""


async def ensure_bootstrap():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(BOOTSTRAP_SQL)


# -------------------- DB Helpers --------------------

async def set_report_category(guild_id: int, category_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO mod_settings (guild_id, report_category_id)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET report_category_id = EXCLUDED.report_category_id, updated_at = NOW()
            """,
            guild_id, category_id,
        )


async def get_report_category(guild_id: int) -> Optional[int]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT report_category_id FROM mod_settings WHERE guild_id = $1",
            guild_id,
        )
        return int(row["report_category_id"]) if row and row["report_category_id"] else None


async def get_enforcement(guild_id: int, user_id: int) -> tuple[str, Optional[datetime]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT status, \"until\" FROM user_enforcement WHERE guild_id = $1 AND user_id = $2",
            guild_id, user_id,
        )
        if not row:
            return "ok", None
        return str(row["status"]), row["until"]


async def put_enforcement(guild_id: int, user_id: int, status: str, until: Optional[datetime], reason: Optional[str]):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_enforcement (guild_id, user_id, status, "until", reason)
            VALUES ($1, $2, $3::enforcement_status, $4, $5)
            ON CONFLICT (guild_id, user_id)
            DO UPDATE SET status = EXCLUDED.status, "until" = EXCLUDED."until", reason = EXCLUDED.reason, created_at = NOW()
            """,
            guild_id, user_id, status, until, reason,
        )


# -------------------- Global slash guard --------------------

async def slash_guard(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return True

    status, until = await get_enforcement(interaction.guild.id, interaction.user.id)
    now = datetime.now(timezone.utc)

    if status == "banned":
        raise app_commands.CheckFailure("You are banned from using this bot in this server.")
    if status == "timeout":
        if until and until > now:
            raise app_commands.CheckFailure(f"You are timed out from the bot until <t:{int(until.timestamp())}:F>.")
        else:
            await put_enforcement(interaction.guild.id, interaction.user.id, "ok", None, None)
    return True


# -------------------- Cog --------------------

class LFGModeration(commands.Cog):
    """Admin config + installs global slash guard for timeouts/bans."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        await ensure_bootstrap()
        if slash_guard not in self.bot.tree.checks:
            self.bot.tree.add_check(slash_guard)

    mod = app_commands.Group(name="lfg_mod", description="Admin tools for LFG moderation")

    @mod.command(name="set_report_category", description="(Admin) Set the category used for LFG report channels.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(category="Pick a category to host per-report channels")
    async def set_report_category_cmd(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        await set_report_category(interaction.guild.id, category.id)
        await interaction.response.send_message(f"Report category set to **{category.name}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LFGModeration(bot))
