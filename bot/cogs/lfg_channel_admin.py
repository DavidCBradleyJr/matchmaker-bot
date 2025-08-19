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


def _err(msg: str) -> str:
    return f"{msg} Please try again."

def is_guild_admin_or_owner():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        if interaction.user.id == getattr(interaction.guild.owner, "id", None):
            return True
        perms = getattr(interaction.user, "guild_permissions", None)
        return bool(perms and (perms.manage_guild or perms.administrator))
    return app_commands.check(predicate)


class LfgChannelAdmin(commands.Cog):
    """
    Admin/Owner-only controls to set/clear the LFG channel for a guild.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    lfg_channel = app_commands.Group(
        name="lfg_channel",
        description="Configure the channel where LFG ads will be posted (admin/owner only).",
    )

    @lfg_channel.command(name="set", description="Set the channel where LFG ads will be posted.")
    @app_commands.describe(channel="The text channel for LFG ads")
    @app_commands.guild_only()
    @is_guild_admin_or_owner()
    async def set_lfg_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # Save to guild_settings.lfg_channel_id
        try:
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool not initialized.")
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO guild_settings (guild_id, lfg_channel_id)
                    VALUES ($1, $2)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET lfg_channel_id = EXCLUDED.lfg_channel_id
                    """,
                    int(interaction.guild_id),
                    int(channel.id),
                )
            await interaction.response.send_message(
                f"✅ LFG channel set to {channel.mention}.", ephemeral=True
            )
        except Exception:
            LOGGER.error("Failed to set LFG channel:\n%s", traceback.format_exc())
            await interaction.response.send_message(
                _err("Something went wrong while saving the LFG channel."), ephemeral=True
            )

    @lfg_channel.command(name="clear", description="Clear the configured LFG channel for this server.")
    @app_commands.guild_only()
    @is_guild_admin_or_owner()
    async def clear_lfg_channel(self, interaction: discord.Interaction):
        try:
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool not initialized.")
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE guild_settings
                    SET lfg_channel_id = NULL
                    WHERE guild_id = $1
                    """,
                    int(interaction.guild_id),
                )
            await interaction.response.send_message(
                "🧹 Cleared the LFG channel for this server.", ephemeral=True
            )
        except Exception:
            LOGGER.error("Failed to clear LFG channel:\n%s", traceback.format_exc())
            await interaction.response.send_message(
                _err("Something went wrong while clearing the LFG channel."), ephemeral=True
            )

    @lfg_channel.command(name="show", description="Show the current LFG channel for this server.")
    @app_commands.guild_only()
    @is_guild_admin_or_owner()
    async def show_lfg_channel(self, interaction: discord.Interaction):
        try:
            pool = get_pool()
            if pool is None:
                raise RuntimeError("DB pool not initialized.")
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT lfg_channel_id FROM guild_settings WHERE guild_id = $1",
                    int(interaction.guild_id),
                )
            if not row or not row["lfg_channel_id"]:
                return await interaction.response.send_message(
                    "ℹ️ No LFG channel configured yet.", ephemeral=True
                )
            channel = interaction.guild.get_channel(int(row["lfg_channel_id"]))
            if channel:
                await interaction.response.send_message(
                    f"📌 Current LFG channel: {channel.mention}", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"📌 Current LFG channel id: `{row['lfg_channel_id']}` (channel not found)",
                    ephemeral=True,
                )
        except Exception:
            LOGGER.error("Failed to show LFG channel:\n%s", traceback.format_exc())
            await interaction.response.send_message(
                _err("Something went wrong while fetching the LFG channel."), ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(LfgChannelAdmin(bot))
