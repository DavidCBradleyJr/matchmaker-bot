from __future__ import annotations

import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class LFGModeration(commands.Cog):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        log.info("LFGModeration cog loaded")

    async def cog_unload(self) -> None:
        log.info("LFGModeration cog unloaded")

    # Example admin-only check (optional). You can attach with @app_commands.check(is_admin).
    async def is_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user or not interaction.guild:
            return False
        perms = interaction.user.guild_permissions  # type: ignore[attr-defined]
        allowed = perms.manage_guild or perms.administrator
        if not allowed and not interaction.response.is_done():
            await interaction.response.send_message(
                "You need Manage Server or Administrator to use this.",
                ephemeral=True,
            )
        return allowed

    # region: Commands

    @app_commands.command(name="lfg-timeout", description="Timeout or un-timeout a user from using the bot.")
    @app_commands.describe(
        member="The member to (un)timeout",
        minutes="Timeout duration in minutes (0 to clear).",
    )
    async def lfg_timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: int,
    ):
        # Example admin gate (optional)
        if not await self.is_admin(interaction):
            return

        try:
            from bot.utils.timeouts import set_timeout, clear_timeout
        except Exception as e:
            await interaction.response.send_message(
                f"Internal error importing timeout utility: {e}", ephemeral=True
            )
            return

        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        if minutes <= 0:
            await clear_timeout(member.id, guild_id)
            await interaction.response.send_message(
                f"Cleared timeout for {member.mention}.", ephemeral=True
            )
            return

        await set_timeout(member.id, guild_id, minutes)
        await interaction.response.send_message(
            f"Timed out {member.mention} from using the bot for {minutes} minute(s).",
            ephemeral=True,
        )

    @app_commands.command(name="lfg-timeout-status", description="Check if a user is timed out from using the bot.")
    @app_commands.describe(member="The member to check")
    async def lfg_timeout_status(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        try:
            from bot.utils.timeouts import is_user_timed_out, get_timeout_expiry
        except Exception as e:
            await interaction.response.send_message(
                f"Internal error importing timeout utility: {e}", ephemeral=True
            )
            return

        member = member or interaction.user  # type: ignore[assignment]
        guild_id = interaction.guild_id
        if guild_id is None:
            await interaction.response.send_message(
                "This command must be used in a server.", ephemeral=True
            )
            return

        timed_out = await is_user_timed_out(member.id, guild_id)
        if not timed_out:
            await interaction.response.send_message(
                f"{member.mention} is not timed out.", ephemeral=True
            )
            return

        expiry_ts = await get_timeout_expiry(member.id, guild_id)
        pretty = f"<t:{int(expiry_ts)}:R>" if expiry_ts else "unknown time"
        await interaction.response.send_message(
            f"{member.mention} is timed out until {pretty}.", ephemeral=True
        )

    # endregion


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LFGModeration(bot))
