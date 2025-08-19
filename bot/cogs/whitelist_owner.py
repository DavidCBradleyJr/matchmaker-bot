from __future__ import annotations

import logging
import os
import traceback
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..db import get_pool

LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    h = logging.StreamHandler()
    LOGGER.addHandler(h)
LOGGER.setLevel(logging.INFO)

OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # set this env var to your Discord user ID


def owner_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        return int(interaction.user.id) == OWNER_ID and OWNER_ID != 0
    return app_commands.check(predicate)


class WhitelistOwner(commands.Cog):
    """
    Whitelist management — visible and executable by the bot OWNER only.
    Set env OWNER_ID to your Discord user id.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    whitelist = app_commands.Group(
        name="whitelist",
        description="Whitelist controls (owner only).",
    )

    async def _ensure_table(self):
        pool = get_pool()
        if pool is None:
            raise RuntimeError("DB pool not initialized.")
        async with pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS whitelist (
                    user_id BIGINT PRIMARY KEY,
                    added_by BIGINT,
                    added_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )

    @whitelist.command(name="add", description="Add a user to the whitelist (owner only).")
    @owner_only()
    async def add(self, interaction: discord.Interaction, user: discord.User):
        try:
            await self._ensure_table()
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO whitelist (user_id, added_by)
                    VALUES ($1, $2)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    int(user.id),
                    int(interaction.user.id),
                )
            await interaction.response.send_message(
                f"✅ Added {user.mention} (`{user.id}`) to whitelist.", ephemeral=True
            )
        except Exception:
            LOGGER.error("whitelist add failed:\n%s", traceback.format_exc())
            await interaction.response.send_message(
                "Something went wrong while updating the whitelist. Please try again.",
                ephemeral=True,
            )

    @whitelist.command(name="remove", description="Remove a user from the whitelist (owner only).")
    @owner_only()
    async def remove(self, interaction: discord.Interaction, user: discord.User):
        try:
            await self._ensure_table()
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM whitelist WHERE user_id = $1",
                    int(user.id),
                )
            await interaction.response.send_message(
                f"🗑️ Removed {user.mention} (`{user.id}`) from whitelist.", ephemeral=True
            )
        except Exception:
            LOGGER.error("whitelist remove failed:\n%s", traceback.format_exc())
            await interaction.response.send_message(
                "Something went wrong while updating the whitelist. Please try again.",
                ephemeral=True,
            )

    @whitelist.command(name="view", description="View the whitelist (owner only).")
    @owner_only()
    async def view(self, interaction: discord.Interaction):
        try:
            await self._ensure_table()
            pool = get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id, added_by, added_at FROM whitelist ORDER BY added_at DESC")
            if not rows:
                return await interaction.response.send_message("Whitelist is empty.", ephemeral=True)

            # Build a small list string, keep minimal
            lines = []
            for r in rows[:50]:  # cap to avoid huge messages
                uid = int(r["user_id"])
                adder = int(r["added_by"]) if r["added_by"] is not None else None
                when = r["added_at"].strftime("%Y-%m-%d")
                lines.append(f"• `<@{uid}>` ({uid}) — added {when}" + (f" by <@{adder}>" if adder else ""))

            msg = "### Whitelist\n" + "\n".join(lines)
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            LOGGER.error("whitelist view failed:\n%s", traceback.format_exc())
            await interaction.response.send_message(
                "Something went wrong while reading the whitelist. Please try again.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(WhitelistOwner(bot))
